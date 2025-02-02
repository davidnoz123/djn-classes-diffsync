# djn-classes-diffsync
A Python class to watch a local directory and efficiently synchronize text files in a remote directory using compressed, unified diffing.
File changes are queued into a multiprocessing pool for faster processing time.

Not currently available in PyPI. Use locally installed git together with pip the version control system support (VCS) to install (or upgrade to) the latest code from the latest branch '0.1'.

```sh
pip install --upgrade git+https://github.com/davidnoz123/djn-classes-diffsync.git@0.1
