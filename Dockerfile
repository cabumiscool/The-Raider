FROM python:3.8-slim-buster

MAINTAINER RazBum Team

COPY ./requirements.txt /Raider/requirements.txt
COPY ./src /Raider/src

RUN PIP_DEFAULT_TIMEOUT=100 pip3 install -r /Raider/requirements.txt

WORKDIR /Raider/src

CMD [ "python3", "launcher.py" ]
