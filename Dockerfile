FROM ubuntu:xenial

COPY . /opt/moto
RUN apt-get update \
    && apt-get install -y python-pip
RUN pip install --upgrade pip
RUN cd /opt/moto && python setup.py install

CMD tail -f /dev/null
