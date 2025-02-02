from setuptools import setup, find_namespace_packages

setup(
    name="djn-classes-diff_sync",
    packages=find_namespace_packages(include=["djn.*"]),
    install_requires=[],  # Common dependencies
)