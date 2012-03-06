import datetime
from pyquery import PyQuery as pq
import re
import requests
from requests import async

today = datetime.datetime.now()
BASE_URL = "http://en.wikinews.org"
CATEGORY_URL = "%s/wiki/Category:%%s" % BASE_URL


def process_page(response):
    doc = pq(response.text)
    published_date = doc.find(".published")
    if published_date:
        published_date = datetime.datetime.strptime(published_date.text(),
                "%A, %B %d, %Y")
    article = pq("<article>")
    is_draft = False
    # import ipdb; ipdb.set_trace()
    for e in doc.find("div.mw-content-ltr").children():
        if e.tag == "center":
            break  # Break as soon as we see the bottom "contribute" call to action
        if e.attrib.get("class", "") in ["infobox", "toc"]:
            continue
        if not is_draft:
            is_draft = "metadata" in e.attrib.get("class", "")
            continue
        article.append(e)

    categories = [a.attrib["href"].split(":")[-1] for a in doc("#catlinks li a")
            if not "_" in a.attrib["href"]]

    article = article.html()
    return {
        "title": doc.find("h1").text(),
        "published_date": published_date,
        "is_draft": is_draft,
        "article": article.strip() if article else "",
        "categories": categories,
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
        from armstrong.apps.articles.models import Article
        from armstrong.core.arm_sections.models import Section

        data = {}
        for i in range(int(number)):
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
            for i in range(len(responses)):
                data[urls[i].url] = process_page(responses[i])
            print "grabbed %d for %s" % (len(responses), date)

        for url in data:
            slug = url.split("/")[-1]
            article = Article.objects.create(
                title=data[url]["title"],
                slug=slug,
                pub_status="D" if data[url]["is_draft"] else "P",
                body=data[url]["article"],
                pub_date=data[url]["published_date"],
            )
            for category in data[url]["categories"]:
                article.sections.add(Section.objects.get_or_create(title=category)[0])

load_demo_data = LoadDemoData()
