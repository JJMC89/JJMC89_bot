#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script deploys editnotices.

The following parameters are required:

-editnotice_template Title of the editnotice template

The following parameters are supported:

-always           Don't prompt to save changes.

-subject_only     Restrict to subject pages

-talk_only        Restrict to talk pages

-to_subject       Add each talk page's subject page

-to_talk          Add each subject page's talk page

&params;
"""
# Author : JJMC89
# License: MIT
from typing import Any, Dict, Generator, Iterable, Set

import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import CurrentPageBot, SingleSiteBot


docuReplacements = {  # pylint: disable=invalid-name
    '&params;': pagegenerators.parameterHelp
}


def get_template_titles(
    templates: Iterable[pywikibot.Page],
) -> Set[pywikibot.Page]:
    """
    Given an iterable of templates, return a set of pages.

    @param templates: iterable of templates (L{pywikibot.Page})
    """
    titles = set()
    for template in templates:
        if template.isRedirectPage():
            template = template.getRedirectTarget()
        if not template.exists():
            continue
        titles.add(template.title(with_ns=template.namespace() != 10))
        for tpl in template.backlinks(filter_redirects=True):
            titles.add(tpl.title(with_ns=tpl.namespace() != 10))
    return titles


def validate_options(
    options: Dict[str, Any], site: pywikibot.site.APISite
) -> bool:
    """
    Validate the options and return bool.

    @param options: options to validate
    """
    pywikibot.log('Options:')
    required_keys = ['editnotice_template']
    has_keys = list()
    for key, value in options.items():
        pywikibot.log('-{} = {}'.format(key, value))
        if key in required_keys:
            has_keys.append(key)
        if key == 'editnotice_template':
            if not isinstance(key, str):
                return False
            options[key] = '{{' + value + '}}'
            editnotice_page = pywikibot.Page(site, value, ns=10)
            if not editnotice_page.exists():
                return False
    if sorted(has_keys) != sorted(required_keys):
        return False
    options['editnotice_page'] = editnotice_page
    return True


def page_with_subject_page_generator(
    generator: Iterable[pywikibot.Page], return_subject_only=False
) -> Generator[pywikibot.Page, None, None]:
    """
    Yield pages and associated subject pages from another generator.

    Only yields subject pages if the original generator yields a non-
    subject page, and does not check if the subject page in fact exists.
    """
    for page in generator:
        if not return_subject_only or not page.isTalkPage():
            yield page
        if page.isTalkPage():
            yield page.toggleTalkPage()


def subject_page_generator(
    generator: Iterable[pywikibot.Page],
) -> Generator[pywikibot.Page, None, None]:
    """Yield subject pages from another generator."""
    for page in generator:
        if not page.isTalkPage():
            yield page


def talk_page_generator(
    generator: Iterable[pywikibot.Page],
) -> Generator[pywikibot.Page, None, None]:
    """Yield talk pages from another generator."""
    for page in generator:
        if page.isTalkPage():
            yield page


def editnotice_page_generator(
    generator: Iterable[pywikibot.Page],
) -> Generator[pywikibot.Page, None, None]:
    """Yield editnotice pages for existing, non-redirect pages from another
    generator."""
    for page in generator:
        if page.exists() and not page.isRedirectPage():
            title = page.title(withSection=False)
            editnotice_title = 'Template:Editnotices/Page/{}'.format(title)
            editnotice_page = pywikibot.Page(page.site, editnotice_title)
            yield editnotice_page


class EditnoticeDeployer(SingleSiteBot, CurrentPageBot):
    """Bot to deploy editnotices."""

    def __init__(self, **kwargs) -> None:
        """Initializer."""
        self.available_options.update(  # pylint: disable=no-member
            {'editnotice_page': None, 'editnotice_template': None}
        )
        super().__init__(**kwargs)
        self.editnotice_page_titles = get_template_titles(
            [self.opt.editnotice_page]
        )
        self.editnotice_template = self.opt.editnotice_template

    def check_disabled(self) -> None:
        """Check if the task is disabled. If so, quit."""
        class_name = self.__class__.__name__
        page = pywikibot.Page(
            self.site,
            'User:{}/shutoff/{}.json'.format(self.site.username(), class_name),
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                pywikibot.error('{} disabled:\n{}'.format(class_name, content))
                self.quit()

    def treat_page(self) -> None:
        """Process one page."""
        self.check_disabled()
        if self.current_page.isRedirectPage():
            text = ''
        else:
            text = self.current_page.text
            wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
            # Check to make sure the editnotice isn't already there.
            for tpl in wikicode.filter_templates():
                if tpl.name.matches(self.editnotice_page_titles):
                    return
        self.put_current(
            '\n'.join((self.editnotice_template, text)),
            summary='Deploying editnotice: ' + self.editnotice_template,
            minor=False,
        )


def main(*args: str) -> bool:
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    """
    options = {
        'subject_only': False,
        'talk_only': False,
        'to_subject': False,
        'to_talk': False,
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    gen_factory = pagegenerators.GeneratorFactory(site)
    for arg in local_args:
        if gen_factory.handleArg(arg):
            continue
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg == 'editnotice_template':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for {}'.format(arg), default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if not validate_options(options, site):
        pywikibot.error('Invalid options.')
        return False
    gen = gen_factory.getCombinedGenerator()
    if options['to_subject']:
        gen = page_with_subject_page_generator(
            gen, return_subject_only=options['subject_only']
        )
    elif options['to_talk']:
        gen = pagegenerators.PageWithTalkPageGenerator(
            gen, return_talk_only=options['talk_only']
        )
    elif options['subject_only']:
        gen = subject_page_generator(gen)
    elif options['talk_only']:
        gen = talk_page_generator(gen)
    gen = editnotice_page_generator(gen)
    for key in ('subject_only', 'talk_only', 'to_subject', 'to_talk'):
        options.pop(key, None)
    gen = pagegenerators.PreloadingGenerator(gen)
    EditnoticeDeployer(generator=gen, site=site, **options).run()
    return True


if __name__ == '__main__':
    main()
