from setuptools import setup

with open('README.md', 'r', encoding='utf-8') as fh:
    long_description = fh.read()

setup(
    name='python_sqlite_log_handler',
    packages=['python_sqlite_log_handler'],
    version='CURRENT_VERSION',
    license='MIT',
    description='SQLite log handler for Python logging module',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Roger Vilà',
    author_email='rogervila@me.com',
    url='https://github.com/rogervila/python_sqlite_log_handler',
    download_url='https://github.com/rogervila/python_sqlite_log_handler/archive/CURRENT_VERSION.tar.gz',
    keywords=['sqlite', 'logging', 'handler'],
    install_requires=[],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.12',
    ],
)
