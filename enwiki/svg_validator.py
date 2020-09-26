#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This validates SVGs using the W3C nu validator.

The following arguments are supported:

-always           Don't prompt to save changes.

&params;
"""
from typing import Any, List

import mwparserfromhell
import pywikibot
import requests
from mwparserfromhell.nodes import Template
from pywikibot.bot import ExistingPageBot, SingleSiteBot
from pywikibot.comms.http import user_agent
from pywikibot.pagegenerators import GeneratorFactory, parameterHelp
from requests.exceptions import Timeout, RequestException


docuReplacements = {'&params;': parameterHelp}  # pylint: disable=invalid-name


class SVGValidatorBot(SingleSiteBot, ExistingPageBot):
    """Bot to validate SVGs."""

    def __init__(self, **kwargs: Any) -> None:
        """Initializer."""
        super().__init__(**kwargs)
        self.nu_session = requests.Session()
        self.nu_session.headers['user-agent'] = user_agent(
            kwargs['site'],
            '{script_product} ({script_comments}) {http_backend} {python}',
        )
        self.nu_session.params = {'level': 'error', 'out': 'json'}

    def teardown(self) -> None:
        """Close the W3C nu validator session."""
        self.nu_session.close()

    def init_page(self, item: Any) -> pywikibot.Page:
        """Re-class the page."""
        page = super().init_page(item)
        try:
            return pywikibot.FilePage(page)
        except ValueError:
            return page

    def skip_page(self, page: pywikibot.Page) -> bool:
        """Sikp the page if it is not an SVG."""
        if not isinstance(page, pywikibot.FilePage) or not page.title(
            with_ns=False
        ).lower().endswith('.svg'):
            return True
        return super().skip_page(page)

    def check_disabled(self) -> None:
        """Check if the task is disabled. If so, quit."""
        if not self.site.logged_in():
            self.site.login()
        page = pywikibot.Page(
            self.site,
            'User:{username}/shutoff/{class_name}.json'.format(
                username=self.site.user(), class_name=self.__class__.__name__
            ),
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                e = '{} disabled:\n{}'.format(self.__class__.__name__, content)
                pywikibot.error(e)
                self.quit()

    def validate_svg(self) -> List[str]:
        """
        Validate a SVG using the W3C Nu validator.

        Returns a list of validation error messages.

        @raises RuntimeError: validation is indeterminate
        @raises AssertionError: 1) response root does not have the messages key
            with a list or 2) request URL does not match the response URL
        """
        url = self.current_page.get_file_url()
        _logger = 'w3c-nu'
        retries = 0
        retry_wait = pywikibot.config.retry_wait
        # API docs: https://github.com/validator/validator/wiki
        while True:
            try:
                response = self.nu_session.get(
                    url='https://validator.w3.org/nu/',
                    params={'doc': url},
                    timeout=pywikibot.config.socket_timeout,
                )
            except Timeout:
                if (
                    retry_wait > pywikibot.config.retry_max
                    or retries == pywikibot.config.max_retries
                ):
                    raise
                pywikibot.exception()
                pywikibot.sleep(retry_wait)
                retries += 1
                retry_wait += pywikibot.config.retry_wait
            else:
                break
        response.raise_for_status()
        pywikibot.debug(response.text, _logger)
        data = response.json()
        assert 'messages' in data and isinstance(
            data['messages'], list
        ), 'Response missing required messages key.'
        assert (
            'url' not in data or data['url'] == url
        ), 'Query for {} returned data on {}.'.format(url, data['url'])
        errors = list()
        warnings = list()
        for message in data['messages']:
            if not isinstance(message, dict):
                pywikibot.error('Message is not an object.')
                continue
            if 'type' not in message:
                pywikibot.error('Message missing required type key.')
                continue
            if message['type'] not in ('non-document-error', 'error', 'info'):
                pywikibot.error(
                    'Unknown message type: {type}.'.format(**message)
                )
                continue
            message.setdefault('message', '')
            message.setdefault('subType', 'none')
            if message['type'] == 'non-document-error':
                raise RuntimeError(
                    'Validation indeterminate. {type}/'
                    '{subType}: {message}'.format(**message)
                )
            if message['type'] == 'error':
                errors.append(message['message'])
            elif message['subType'] == 'warning':
                warnings.append(message['message'])
            else:
                pywikibot.debug(str(message), _logger)
        return errors

    def treat_page(self) -> None:
        """Process one page."""
        self.check_disabled()
        try:
            errors = self.validate_svg()
        except (AssertionError, RequestException, RuntimeError):
            pywikibot.exception()
            return
        summary = 'Tagging {} SVG'
        if errors:
            summary = summary.format('invalid')
            new_tpl = Template('Invalid SVG')
            new_tpl.add('1', len(errors))
        else:
            summary = summary.format('valid')
            new_tpl = Template('Valid SVG')
        wikicode = mwparserfromhell.parse(
            self.current_page.text, skip_style_tags=True
        )
        for tpl in wikicode.ifilter_templates():
            if tpl.name.matches({'Valid SVG', 'Invalid SVG'}):
                wikicode.replace(tpl, new_tpl)
                break
        else:
            wikicode.insert(0, str(new_tpl) + '\n')
        self.put_current(str(wikicode), summary=summary)


def main(*args: str) -> None:
    """Process command line arguments and invoke bot."""
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    gen_factory = GeneratorFactory(site)
    for arg in local_args:
        if gen_factory.handleArg(arg):
            continue
        arg, _, _ = arg.partition(':')
        arg = arg[1:]
        options[arg] = True
    gen = gen_factory.getCombinedGenerator(preload=True)
    SVGValidatorBot(generator=gen, site=site, **options).run()


if __name__ == '__main__':
    main()
