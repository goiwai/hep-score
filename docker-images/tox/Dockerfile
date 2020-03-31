FROM cern/cc7-base:latest
ENV PATH="/usr/bin"
RUN yum install -y git gcc python-devel rh-python35
RUN curl -o /root/get-pip.py https://bootstrap.pypa.io/get-pip.py
RUN python /root/get-pip.py
RUN pip install --upgrade tox coverage
RUN scl enable rh-python35 'python /root/get-pip.py'
RUN scl enable rh-python35 'pip install --upgrade tox coverage'
