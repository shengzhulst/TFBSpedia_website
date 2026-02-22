# The Django part for TFBSpedia database

This is the Django part of the TFBSpedia database with based on the free template from [Django Soft](https://app-generator.dev/django-soft) starter provided by [Django App Generator](https://app-generator.dev/tools/django-generator/).

## Dependencies:



django==4.2.8

gunicorn==21.2.0

whitenoise==6.6.0

python-dotenv==1.0.1

django-admin-soft-dashboard

psycopg2-binary

djangorestframework

markdown 
      
django-filter  

## Manual Build 

> Install modules via `VENV`  

```bash
$ pip install virtualenv
$ virtualenv env
$ source env/bin/activate
$ pip install -r requirements.txt
```

<br />

> `Set Up Database`

```bash
$ python manage.py makemigrations
$ python manage.py migrate
```

<br />

> `Start the App`

```bash
$ python manage.py runserver
```

At this point, the app runs at `http://127.0.0.1:8000/`. 

<br />

---

