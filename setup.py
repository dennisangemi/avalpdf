import os
import re
from setuptools import setup, find_packages

# Read version from version.py without importing the package
with open(os.path.join('avalpdf', 'version.py'), 'r') as f:
    version_match = re.search(r'^__version__ = [\'"]([^\'"]*)[\'"]', f.read(), re.M)
    if version_match:
        version = version_match.group(1)
    else:
        raise RuntimeError('Unable to find version string in version.py')

# Read long description from README.md
with open('README.md', 'r', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='avalpdf',
    version=version,
    description='PDF Accessibility Validator',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Dennis Angemi',
    author_email='dennisangemi@gmail.com',
    url='https://github.com/dennisangemi/avalpdf',
    packages=find_packages(),
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'avalpdf=avalpdf:main',
        ],
    },
    install_requires=[
        'pdfix-sdk',
        'requests',
        'rich'
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)