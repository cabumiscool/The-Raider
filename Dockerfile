FROM ubuntu:20.04

MAINTAINER RazBum Team

RUN apt-get update -y
RUN apt-get upgrade -y
RUN apt-get install -y python3-pip python3-dev

COPY ./requirements.txt /Raider/requirements.txt
COPY ./src /Raider/src

RUN PIP_DEFAULT_TIMEOUT=100 pip3 install -r /Raider/requirements.txt

WORKDIR /Raider/src

ENTRYPOINT [ "python3" ]

CMD [ "launcher.py" ]
