# PRIMEval webserver (Django, PostgreSQL, Gunicorn, NGINX)

Development, Staging and Production versions are provided.
Use the Development environment for development and to run database migrations (not possible in the Development environment).
Use the Staging environment for setting up the production environment. For the Staging setup, a public domain is required for the Let's Encrypt setup and HTTPS access (HTTP works without).
Once everything works, switch to the Production environmentfor issuing the Let's Encrypt production certificate.
It is possible to directly use the staging/production environments.

## Staging/Production environment

### Description

* Uses Django on Gunicorn + NGINX.
* The server is available at under your public domain as s set up in the .env.prod files.
* No mounted folders, all data is saved in Docker volumes.
* To apply changes, the image must be re-built.

### Notes

Use different docker-compose configuration files to switch between the staging and production environments:
* docker-compose.prod.yml
* docker-compose.staging.yml

### Environment variables setup

* Rename .env.prod-sample to .env.prod and .end.prod.db-sample to .end.prod.db.
* Rename .env.prod.proxy-companion-sample to .env.prod.proxy-companion and .end.staging.proxy-companion-sample to .end.staging.proxy-companion
* Update the environment variables in the .env and docker-compose.yml files.

### Bringing up the production environment using following command:
```
docker-compose -f docker-compose.staging.yml up -d --build
```

### When running for the first time (or if required)

* Migrate the database
```
docker-compose -f docker-compose.staging.yml exec web python manage.py migrate --no-input
```

* Collect the static files
```
docker-compose -f docker-compose.staging.yml exec web python manage.py collectstatic --no-input  
```

* Create the createsuperuser
```
docker-compose -f docker-compose.staging.yml exec web python manage.py createsuperuser
```

### Bringing the system down

Bring the system down
```
docker-compose -f docker-compose.staging.yml down
```

### Final setup

Once everything works, use the production environment
```
docker-compose -f docker-compose.prod.yml up -d --build
docker-compose -f docker-compose.prod.yml down
```




## Development environment

### Description

* Uses the default Django development server.
* The server is available at [http://localhost:8000](http://localhost:8000).
* The "app" folder is mounted into the container so that changes are applied directly.

### Environment variables setup

* Rename .env.dev-sample to .env.dev and .end.dev.db-sample to .end.dev.db.
* Update the environment variables in the .env.dev, .env.dev.db and docker-compose.yml files.

### Bringing up the development environment using following command:
```
docker-compose -f docker-compose.yml up -d --build
```

### When running for the first time (or if required)

* Migrate the database
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

### Bringing the system down

Make sure not to use the -v option, otherwise the volumes will be deleted and all data will be lost.
```
docker-compose -f docker-compose.yml down
```


# Miscellaneous

## Backup the static, media and postgres volume


```
# get the container id of primeval_docker_web and postgres:14.0-alpine
docker container ls

# Pack and compress the folders from the Docker volumes into an archive into the local folder
docker run --rm --volumes-from e33d5e0b5883 -v $(pwd):/backup busybox tar zcvf /backup/media.tar.gz /home/app/web/media/
docker run --rm --volumes-from e33d5e0b5883 -v $(pwd):/backup busybox tar zcvf /backup/static.tar.gz /home/app/web/static/
docker run --rm --volumes-from 2fa969496e87 -v $(pwd):/backup busybox tar zcvf /backup/postgres.tar.gz /var/lib/postgresql/data/
```



## Restore data into Django volumes

```
# pack and compress all media files in a tar.gzfile
cd media
tar zcvf media.tar.gz *

# get the container id for primeval_docker_web (e.g. 5e85aff7eb59)
docker container ls

# copy the compressed file by specifying the container id
docker cp media.tar.gz 5e85aff7eb59:/home/app/web/media/media.tar.gz

# use a dummy ubuntu container to mount the volume, uncompress and delete the archive
docker run -v primeval_docker_media_volume:/data -it ubuntu bash

# in the ubuntu bash
cd /data
tar xvfz media.tar.gz
rm media.tar.gz
exit

# Example for copying the PostgreSQL data
docker cp postgres.tar.gz 01a40a19a099:/var/lib/postgresql/data/postgres.tar.gz
```



## Django database export/import

Export database from (non-dockerized) Django:

```
python manage.py dumpdata --natural-foreign --exclude=auth.permission --exclude=contenttypes --indent=4 > data.json
```

Transfer the  file to the new environment, rebuild the development container, and import the data.

Log in into **Development** environment using bash, then load the data:

```
docker compose -f docker-compose.yml exec web
python manage.py loaddata data.json
exit
```

Finally, delete the JSON file again and rebuild the containers.



## Docker cheat sheet

```
# Stop the container(s) using the following command:
docker-compose down --remove-orphans

# Delete all containers using the following command:
docker rm -f $(docker ps -a -q)

# Delete all volumes using the following command:
docker volume rm $(docker volume ls -q)

# Restart the containers using the following command:
docker-compose up -d

# List contents in all docker volumes
for i in `docker volume ls -q`; do echo "volume: ${i}"; docker run --rm -it -v ${i}:/vol alpine:latest ls /vol; echo; done;
```

## Links

* https://testdriven.io/blog/dockerizing-django-with-postgres-gunicorn-and-nginx/
* https://testdriven.io/blog/django-lets-encrypt/
