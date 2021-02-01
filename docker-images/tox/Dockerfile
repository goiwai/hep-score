FROM cern/cc7-base:latest
RUN \
    yum install -y git gcc openldap-devel krb5-devel mariadb-devel python2-pip python3-pip which && \
    yum clean all --enablerepo='*' && \
    python3 -m pip install --upgrade pip wheel; \
    python3 -m pip install tox coverage; \