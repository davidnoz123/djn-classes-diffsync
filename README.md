# djn-classes-diffsync
A Python class to watch a local directory and efficiently synchronize text files in a remote directory using compressed, unified diffing.
File changes are queued into a multiprocessing pool for faster response time.

Not currently available in PyPI. Use locally installed git together with pip version control system support (VCS) to install the latest code from the latest branch '0.1'.

```sh
pip install git+https://github.com/davidnoz123/djn-classes-diffsync.git@0.1
