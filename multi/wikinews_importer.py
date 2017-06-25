#!/usr/bin/env python
# -*- coding: utf-8 -*-
##########################################################################################
# Task             : Wikinews Importer
#                    see https://en.wikipedia.org/wiki/User:Wikinews_Importer_Bot
# Original author  : Misza13 / Misza (https://meta.wikimedia.org/wiki/User:Misza13 / 
#                    https://wikitech.wikimedia.org/wiki/User:Misza)
# Original source  : wikinews-importer.py in wikinews-importer on Wikimedia Tool Labs
#                    (https://tools.wmflabs.org/?tool=wikinews-importer)
# Modified by      : JJMC89
##########################################################################################
# pylint: disable=all
import sys
import re
import traceback
import simplejson
import pywikibot
from pywikibot.data import api
from xml.dom.minidom import parseString as minidom_parseString
from xml.dom import Node


MONTHS = [u'January',u'February',u'March',u'April',u'May',u'June',u'July',u'August',u'September',u'October',u'November',u'December',
    u'Janvier',u'Février',u'Mars',u'Avril',u'Mai',u'Juin',u'Juillet',u'Août',u'Septembre',u'Octobre',u'Novembre',u'Décembre'] #TODO: srsly...
date_rx = re.compile(r'(\d+) (%s) (\d\d\d\d)' % ('|'.join(MONTHS),), re.IGNORECASE)


def parseNews(page):
    #pywikibot.output(page.title(asLink=True))
    site = page.site
    #response, data = pywikibot.comms.http.request(site, '/w/api.php', {'action':'parse','format':'json','page':page.title()})
    rq = api.Request(site=site, action='parse', format='json', page=page.title())
    data = rq.submit()
    #print data
    #text = simplejson.loads(data)['parse']['text']['*']
    text = data['parse']['text']['*']
    #print text

    #doc = minidom_parseString(u'<html><body>' + text.encode('utf-8') + u'</body></html>')
    doc = minidom_parseString((u'<html><body>' + text + u'</body></html>').encode('utf-8'))

    ul = doc.getElementsByTagName('ul')
    if ul:
        for li in ul[0].getElementsByTagName('li'):
            if li.firstChild.nodeType == Node.TEXT_NODE:
                prefix = li.firstChild.nodeValue
                if site.lang == 'en':
                    prefix = date_rx.sub(r'[[\2 \1]]',prefix)
                elif site.lang == 'fr':
                    prefix = date_rx.sub(r'{{date|\1|\2|\3}}',prefix)
            else:
                prefix = ''
            yield prefix, pywikibot.Page(site, li.getElementsByTagName('a')[0].getAttribute('title'))


def doOnePage(tpl, page, site_src):
    #pywikibot.output(page.title(asLink=True))
    txt = page.get().replace('_', ' ')
    rx = re.search(r'{{(%s\|.*?)}}' % (tpl.title()), txt)
    if not rx:
        return

    config = {
            'page' : (None, False),
            'indent' : (u'*', False),
            }

    raw_config = rx.group(1).split('|')[1:]
    for x in raw_config:
        var, val = x.split('=',1)
        var, val = var.strip(), val.strip()
        config[var] = (val, True)

    if not config['page'][0]:
        pywikibot.output(u'No target page specified!')

    newsPage = pywikibot.Page(site_src, config['page'][0])

    text = u'\n'.join(
            [u'%(indent)s %(prefix)s[[wikinews:%(lang)s:%(article_page)s|%(article_title)s]]' % {
                    'article_page' : re.sub(r'[\s\xa0]', ' ', news.title()),
                    'article_title' : news.title(),
                    'prefix' : prefix,
                    'indent' : config['indent'][0],
                    'lang' : site_src.lang }
                for prefix, news in parseNews(newsPage)]
            )

    #Check for old content
    oldtext = page.get()
    #Ignore lead (timestamp etc.)
    rx = re.compile('^(.*)<noinclude>.*', re.DOTALL)
    oldtext = rx.sub(r'\1', oldtext).strip()

    if text != oldtext:
        raw_config = '|'.join(u'%s = %s' % (v,k[0]) for v,k in config.items() if k[1])
        text = u'%(text)s<noinclude>\n{{%(tpl)s|%(config)s}}\nRetrieved by ~~~ from [[wikinews:%(lang)s:%(page)s|]] on ~~~~~\n</noinclude>' % {
                'text' : text,
                'tpl' : tpl.title(),
                'config' : raw_config,
                'page' : config['page'][0],
                'lang' : site_src.lang,
                }
        #pywikibot.output(text)
        page.put(text, summary=u'Updating from [[n:%s|%s]]' % (newsPage.title(),newsPage.title(),))

    return {
        'src' : newsPage.title(),
        'ns'  : page.site.namespace(page.namespace()),
        'dst' : page.title(),
        }


def main(lang_src, lang_dest):
    pages_maintained = {}
    site_src = pywikibot.Site(code = lang_src, fam = 'wikinews')
    site_dest = pywikibot.Site(code = lang_dest, fam = 'wikipedia')
    tpl = pywikibot.Page(site_dest, 'User:Wikinews Importer Bot/config')
    for page in tpl.getReferences(onlyTemplateInclusion=True):
        if page.title().endswith('/Wikinews') or page.title().startswith('Template:Wikinewshas/') or '/Wikinews/' in page.title():
        #if page.title() == 'Portal:Current events/Wikinews':
            try:
                step = doOnePage(tpl, page, site_src)
                if step['ns'] not in pages_maintained:
                    pages_maintained[step['ns']] = []
                pages_maintained[step['ns']].append(step)
            except KeyboardInterrupt:
                break
            except:
                pywikibot.output(page.title(asLink=True))
                traceback.print_exc()

    audit_txt = u''
    for ns in sorted(pages_maintained.keys()):
        audit_txt += '\n\n== %s: ==\n\n' % ns
        items = sorted(pages_maintained[ns], key=lambda x: x['dst'])
        audit_txt += '\n'.join('# [[%(dst)s]] &larr; [[n:%(src)s|%(src)s]]' % item for item in items)
    audit_txt = audit_txt.strip()

    audit_page = pywikibot.Page(site_dest,'User:Wikinews Importer Bot/List')
    oldtext = audit_page.get()
    rx = re.compile('^.*?(?=\n== )', re.DOTALL)
    oldtext = rx.sub('', oldtext).strip()
    #pywikibot.showDiff(oldtext, audit_txt)
    if oldtext != audit_txt:
        audit_page.put(
            u'List of pages maintained by ~~~ by namespace\n\nLast updated: ~~~~~\n\n' + audit_txt,
            comment='Updating list of maintained pages (%d items).' % sum(len(i) for i in pages_maintained.values()),
            )

if __name__ == '__main__':
    try:
        if len(sys.argv) == 1:
            lang_src = 'en'
            lang_dest = lang_src
        elif sys.argv[1] == 'test':
            lang_src = 'en'
            lang_dest = 'test'
        else:
            lang_src = sys.argv[1]
            lang_dest = lang_src
        main(lang_src, lang_dest)
    finally:
        pywikibot.stopme()
