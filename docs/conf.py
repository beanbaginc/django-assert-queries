import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(__file__, '..', '..')))

from beanbag_docutils.sphinx.ext.github import github_linkcode_resolve

import django_assert_queries


project = 'django-assert-queries'
copyright = '2024, Beanbag, Inc.'
author = 'Beanbag, Inc.'

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'sphinx.ext.linkcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.todo',
    'beanbag_docutils.sphinx.ext.autodoc_utils',
    'beanbag_docutils.sphinx.ext.extlinks',
    'beanbag_docutils.sphinx.ext.http_role',
    'beanbag_docutils.sphinx.ext.ref_utils',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'furo'
html_static_path = ['_static']


intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

extlinks = {
    'pypi': ('https://pypi.org/project/%s/', '%s'),
}


autodoc_member_order = 'bysource'
autoclass_content = 'class'
autodoc_default_flags = [
    'members',
    'special-members',
    'undoc-members',
    'show-inheritance',
]
autodoc_excludes = {
    '*': [
        '__annotations__',
        '__closed__',
        '__dataclass_fields__',
        '__dataclass_params__',
        '__dict__',
        '__doc__',
        '__extra_items__',
        '__match_args__',
        '__module__',
        '__mutable_keys__',
        '__optional_keys__',
        '__orig_bases__',
        '__readonly_keys__',
        '__required_keys__',
        '__total__',
        '__weakref__',
    ],
    'class': [
        # Common to models.
        'DoesNotExist',
        'MultipleObjectsReturned',

        # Common to forms.
        'base_fields',
        'media',
    ],
}

add_function_parentheses = True


autosummary_generate = True
napolean_beanbag_docstring = True
napolean_google_docstring = False
napolean_numpy_docstring = False


def linkcode_resolve(domain, info):
    major, minor, micro, tag, release_num, released = \
        django_assert_queries.VERSION
    is_final = (tag == 'final')

    if is_final or release_num > 0:
        branch = f'release-{major}'

        if released:
            branch += f'.{minor}'

            if micro:
                branch += f'.{micro}'

            if not is_final:
                branch += tag

                if release_num:
                    branch += str(release_num)
        else:
            branch += '.x'
    else:
        branch = 'main'

    return github_linkcode_resolve(
        domain=domain,
        info=info,
        allowed_module_names=['django_assert_queries'],
        github_org_id='beanbaginc',
        github_repo_id='django-assert-queries',
        branch=branch)
