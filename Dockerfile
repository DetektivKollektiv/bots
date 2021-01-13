FROM python:3.8-slim

# set the working directory in the container
WORKDIR /code

# copy the dependencies file to the working directory
COPY requirements.txt .

# install dependencies
RUN pip install -r requirements.txt

# copy the content of the local src directory to the working directory
COPY src/ .

# set Stage environment variable
ARG STAGE
ENV STAGE=$STAGE

# command to run on container start
CMD [ "python", "./telegram_bot.py" ]