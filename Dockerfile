FROM joyzoursky/python-chromedriver:latest

LABEL maintainer="dmintz"


RUN apt-get -y update
COPY ./requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt
RUN pip install --upgrade pip
RUN pip install selenium

COPY . /app
WORKDIR /app

RUN mkdir -p /app/logs

ENV TZ='UTC'

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh
RUN ln -s usr/local/bin/docker-entrypoint.sh /
ENTRYPOINT ["docker-entrypoint.sh"]