DEBUG = True
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'test.db',
    }
}


# Make this unique, and don't share it with anybody.
SECRET_KEY = 'af=y9ydd51a0g#bevy0+p#(7ime@m#k)$4$9imoz*!rl97w0j0'


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'django.contrib.staticfiles',
    'django_assert_queries.tests',
]
