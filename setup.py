from setuptools import setup, find_namespace_packages

setup(
    name="djn-classes-diffsync",
    packages=find_namespace_packages(include=["djn.*"]),
    install_requires=[],  # Common dependencies
)
