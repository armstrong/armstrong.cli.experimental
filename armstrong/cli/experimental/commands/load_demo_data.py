import datetime
from pyquery import PyQuery as pq
import re

today = datetime.datetime.now()
BASE_URL = "http://en.wikinews.org"
CATEGORY_URL = "%s/wiki/Category:%%s" % BASE_URL


def process_page(response):
    text = response.text
    doc = pq(text)
    published_date = doc.find(".published")
    if published_date:
        try:
            published_date = datetime.datetime.strptime(published_date.text().strip(),
                "%A, %B %d, %Y")
        except:
            published_date = datetime.datetime.now()
    else:
        published_date = datetime.datetime.now()

    dom_images = doc('img.thumbimage')
    images = ['http://upload.wikimedia.org/wikipedia/commons/%s' % 
            '/'.join(img.attrib['src'].split('/')[-4:-1])
            for img in dom_images]

    article = pq("<article>")
    is_draft = False
    for e in doc.find("div.mw-content-ltr").children():
        if e.tag == "center":
            break  # Break as soon as we see the bottom "contribute" call to action
        if e.attrib.get("class", "") in ["infobox", "toc"]:
            continue
        if e.attrib.get("class", "").find("thumb") != -1:
            continue
        if not is_draft:
            is_draft = "metadata" in e.attrib.get("class", "")
            if is_draft:
                continue
        if e.tag == "h2":
            h2 = pq("<h2>").text(pq(".mw-headline", e).text())
            article.append(h2)
        else:
            article.append(e)

    categories = [a.attrib["href"].split(":")[-1] for a in doc("#catlinks li a")
            if not "_" in a.attrib["href"]]

    article = article.html()
    p_tags = pq(article).children().not_("div")
    summary = p_tags[2].text_content() if len(p_tags) >= 3 else ""
    return {
        "title": doc.find("h1").text(),
        "images": images,
        "published_date": published_date,
        "is_draft": is_draft,
        "article": article.strip() if article else "",
        "categories": categories,
        "summary": summary,
    }


def is_recap_post(a):
    return bool(re.findall(r"\d{4}/\w+/\d{1,2}$", a.attrib["href"]))


class LoadDemoData(object):
    """
    Load in initial demo data from WikiNews
    """
    requires_armstrong = True

    def build_parser(self, parser):
        parser.add_argument('--number', default='5',
                help='location to start a new Armstrong project')

    def __call__(self, number=5, **kwargs):
        self.create_front_page_well()
        self.fetch_articles(number)

    def create_front_page_well(self):
        from armstrong.core.arm_wells.models import Well
        from armstrong.core.arm_wells.models import WellType
        well_type, created = WellType.objects.get_or_create(
                title="Front Page", slug="front_page")
        Well.objects.create(type=well_type,
                pub_date=datetime.datetime.now())

    def fetch_articles(self, number_of_days):
        from armstrong.apps.articles.models import Article
        from armstrong.core.arm_sections.models import Section
        from armstrong.apps.images.models import Image
        from armstrong.apps.related_content.models import RelatedContent, RelatedType
        from django.template.defaultfilters import slugify
        from django.conf import settings
        from StringIO import StringIO
        import requests
        from requests import async

        data = {}
        for i in range(int(number_of_days)):
            date = today - datetime.timedelta(days=i)
            url = CATEGORY_URL % (date.strftime("%B_%%d,_%Y") % date.day)
            response = requests.get(url)
            if response.status_code != 200:
                raise Exception("Unable to process response: %d" % response.status_code)
                continue
            doc = pq(response.text)
            urls = []
            for a in doc.find("div.mw-content-ltr li a"):
                if is_recap_post(a):
                    continue
                slug = a.attrib["href"].split("/")[-1]
                if Article.objects.filter(slug=slug).count() > 0:
                    continue
                urls.append(async.get("%s%s" % (BASE_URL, a.attrib["href"])))

            responses = async.map(urls)
            for resp in responses:
                if not resp.error:
                    data[resp.url] = process_page(resp)
            print "grabbed %d for %s" % (len(responses), date)

        lead_art, c = RelatedType.objects.get_or_create(title='lead_art')
        interstitial, c = RelatedType.objects.get_or_create(title='interstitial')
        for url in data:
            print 'loading %s...' % data[url]['title']
            slug = url.split("/")[-1]
            article = Article.objects.create(
                title=data[url]["title"],
                slug=slugify(slug),
                pub_status="D" if data[url]["is_draft"] else "P",
                body=data[url]["article"],
                pub_date=data[url]["published_date"],
                summary=data[url]["summary"]
            )

            for category in data[url]["categories"]:
                article.sections.add(Section.objects.get_or_create(title=category,
                        slug=slugify(category))[0])

            requests = [async.get(u) for u in data[url]["images"]]
            responses = async.map(requests)
            for i, resp in enumerate(responses):
                name = resp.url.split('/')[-1]
                path = ''.join((settings.ARMSTRONG_IMAGES_UPLOAD_PATH,
                                name))
                with open('/'.join((settings.MEDIA_ROOT, path)),
                          'wb') as f:
                    f.write(resp.content)
                img = Image.objects.create(
                    image=path,
                    title=name,
                    slug=slugify(name),
                    pub_status="P",
                    pub_date=datetime.datetime.now(),
                    summary=name
                    )
                RelatedContent.objects.create(
                        source_object=article,
                        destination_object=img,
                        related_type=(lead_art if i < 1 else interstitial),
                        order=i
                )

        # delete all singleton
        Section.objects.annotate(count=Count('content_content_alternates'))\
                .filter(count__lt=2).delete()




load_demo_data = LoadDemoData()
