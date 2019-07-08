from setuptools import find_packages, setup

setup(
    name='flask-common',
    version='0.1',
    url='http://github.com/closeio/flask-common',
    license='MIT',
    description='Close.io internal flask helpers',
    platforms='any',
    classifiers=[
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
    ],
    packages=find_packages(),
    test_suite='tests',
    tests_require=[
        'python-dateutil',
        'pytz',
        'flask',
        'mongoengine',
        'pycrypto',
        'padding',
        'pytest',
    ],
)
