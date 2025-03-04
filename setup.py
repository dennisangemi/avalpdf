from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name='avalpdf',
    version='0.1.4',
    author="Dennis Angemi",
    description="A command-line tool for validating PDF accessibility, analyzing document structure, and generating detailed reports",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author_email="dennisangemi@gmail.com",
    url="https://github.com/dennisangemi/avalpdf",
    packages=find_packages(),
    install_requires=[
        'pdfix-sdk',
        'requests',
        'rich' 
    ],
    entry_points={
        'console_scripts': [
            'avalpdf = avalpdf.cli:main',
        ],
    },
)