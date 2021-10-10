# PRIMEval webserver (Django, PostgreSQL, Gunicorn, NGINX)

Development, Staging and Production versions are provided. It is possible to directly use the staging/production environments.
* Use the Development environment for development and to run database migrations (not possible in the Development environment).
* Use the Staging environment for setting up the Production environment. For the Staging setup, a public domain is required for the Let's Encrypt setup and HTTPS access (HTTP works without public domain).
* Once everything works, switch to the Production environment for issuing the Let's Encrypt production certificate.


## Staging/Production environment

### Description

* Uses Django + Gunicorn, NGINX, PostgreSQL.
* The server is available under your public domain as set up in the .env.prod file.
* No mounted folders, all data is saved in Docker volumes.
* To apply changes, the image must be re-built.

Use different docker-compose configuration files to switch between the staging and production environments:
* docker-compose.prod.yml
* docker-compose.staging.yml

Set up the app using the Staging environment (which will produce an invalid SSL certificate). Once everything is running, switch over to the Production app which will generate a valid SSL certificate.

### Environment variables setup

* Rename _.env.prod-sample_ to _.env.prod_.
* Rename _.env.prod.db-sample_ to _.env.prod.db_.
* Rename _.env.{prod|staging}.proxy-companion-sample_ to _.end.{prod|staging}.proxy-companion_.
* Update the environment variables in the _.env.{prod|staging}*_ and _docker-compose.{prod|staging}.yml_ files.

### Starting and stopping the Staging/Production app:

```
# Starting the app
docker-compose -f docker-compose.{prod|staging}.yml up -d --build

# Stopping the app
docker-compose -f docker-compose.{prod|staging}.yml down
```

### When running for the first time (or if required)

```
# Migrate the database
docker-compose -f docker-compose.{prod|staging}.yml exec web python manage.py migrate --no-input

# Collect the static files
docker-compose -f docker-compose.{prod|staging}.yml exec web python manage.py collectstatic --no-input  

# Create the createsuperuser
docker-compose -f docker-compose.{prod|staging}.yml exec web python manage.py createsuperuser
```

### Final setup

```
docker-compose -f docker-compose.{prod|staging}.yml up -d --build
docker-compose -f docker-compose.{prod|staging}.yml down
```

## Development environment

### Description

* Uses the default Django built-in development server + PostgreSQL.
* The server is available at [http://localhost:8000](http://localhost:8000).
* The "app" folder is mounted into the container so that changes are applied directly.

### Environment variables setup

* Rename _.env.dev-sample_ to _.env.dev_ and _.end.dev.db-sample_ to _.end.dev.db_.
* Update the environment variables in the _.env.dev_, _.env.dev.db_ and _docker-compose.yml_ files.

### Starting and stopping the Development app:

```
# Starting the app
docker-compose -f docker-compose.yml up -d --build

# Stopping the app
docker-compose -f docker-compose.yml down
```

### When running for the first time (or if required)

```
# Making the database migrations
docker-compose -f docker-compose.yml exec web python manage.py makemigrations --no-input

# Database migrations
docker-compose -f docker-compose.yml exec web python manage.py migrate --no-input

# Collect the static files
docker-compose -f docker-compose.yml exec web python manage.py collectstatic --no-input

# Create the createsuperuser
docker-compose -f docker-compose.yml exec web python manage.py createsuperuser
```



# Miscellaneous

## Backup the media folder

```
# Get the container id of primeval_docker_web
docker container ls

# Pack and compress the folders from the Docker volumes into an archive into the local folder
docker run --rm --volumes-from {container-id} -v $(pwd):/backup busybox tar zcvf /backup/media.tar.gz --directory=/home/app/web/media/ .
```

## Restore the media folder

```
# get the container id for primeval_docker_web
docker container ls

# copy the compressed file by specifying the container id
docker cp media.tar.gz {container-id}:/home/app/web/media/media.tar.gz

# use a dummy ubuntu container to mount the volume, uncompress and delete the archive
docker run -v primeval_docker_media_volume:/data -it ubuntu bash
cd /data
tar xvfz media.tar.gz
rm media.tar.gz
exit
```

## Django database export/import

```
# Export database from (non-dockerized) Django:
python manage.py dumpdata --natural-foreign --exclude=auth.permission --exclude=contenttypes --indent=4 > data.json


# Transfer _data.json_ to the _app_ folder on the host and start the Development app to import the data.
mv data.json app/data.json
docker-compose -f docker-compose.yml up -d --build
docker compose -f docker-compose.yml exec web python manage.py loaddata data.json
rm data.json
```

## Docker cheat sheet

```
# Stop the container(s) using the following command:
docker-compose down --remove-orphans

# Delete all containers using the following command:
docker rm -f $(docker ps -a -q)

# Delete all volumes using the following command (data will be lost):
docker volume rm $(docker volume ls -q)

# Restart the containers using the following command:
docker-compose up -d

# List contents in all docker volumes
for i in `docker volume ls -q`; do echo "volume: ${i}"; docker run --rm -it -v ${i}:/vol alpine:latest ls /vol; echo; done;
```

## Links

* [Dockerizing Django with Postgres, Gunicorn, and Nginx](https://testdriven.io/blog/dockerizing-django-with-postgres-gunicorn-and-nginx/)
* [Securing a Containerized Django Application with Let's Encrypt](https://testdriven.io/blog/django-lets-encrypt/)
