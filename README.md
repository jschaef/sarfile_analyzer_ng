# sarfile_analyzer_ng

This project is a fork of my original project <https://github.com/jschaef/sar_file_analyzer> for graphical presentations of linux sar files.
The app is using streamlit, altair, pandas, polars and other great
python modules.
The newer code stream computes data frames from polars rather then from
pandas due to polars more efficient handling of data frames.
Pandas is still used for for better visualization in the streamlit web application.

## live demo

you might have a look here for a live demo:
<https://share.streamlit.io/jschaef/sar_file_analyzer/main/code/first_st.py>.
Create your own account or use the credentials <code>admin/password</code> for
login. Afterwards upload an ascii sar file via the _"Manage Sar File"_ menu on the
top menu. Change to the _"Analyze Data"_ menu. Investigate the diagrams and/or
play with the other menus.

## requirements

* pyhton3
* python3x-pip*
* python3x-tk*
* python modules specified in requirements.txt
* sar files with '.' as decimal separator (LC_NUMERIC en,us)
* 8GB RAM for better user experience

## build

```bash
bash~: cd sar_file_analyzer/code
bash~: python3x -m venv venv, e.g. python3.11 -m venv venv
bash~: source venv/bin/activate
bash~: pip install -U pip
bash~: pip install -r requirements.txt
bash~: install nodejs-common via your package manager (you need the npm binary)
```

## configure

* edit config.py
* edit code/.streamlit/config.toml

## run

* <code>streamlit run start_sar_analyzer.py</code>

## access

* open a webbrowser and navigate to the page displayed before
* username admin/password
* change password of admin
* upload your first ASCII sar file via option menu "Manage Sar Files"

## note

Newer versions of sarfile_analyzer_ng may rely on the latest streamlit version.
Such when pulling the newest git changes it might be that it is not working
within your old virtual environment.
In this case do a <code>pip install -U streamlit</code>

## configuring streamlit

below a sample config.toml. Put it into code/.streamlit/config.toml

```toml
[global]
dataFrameSerialization = "legacy"

[server]
maxUploadSize = 1000

[theme]
primaryColor="#6eb52f"
backgroundColor="#f0f0f5"
secondaryBackgroundColor="#e0e0ef"
textColor="#262730"
font="sans serif"
```

## run app behind nginx

```txt
server {
    listen              443 ssl;
    server_name         <fqdn of your server>;
    ssl_certificate     /etc/ssl/server/<pub_cert>.crt.pem;
    ssl_certificate_key /etc/ssl/private/<priv_key>.key.pem;
    
    location / {
            client_max_body_size 2048M;
            proxy_pass http://127.0.0.1:8501;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "Upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_read_timeout 86400;
    }
}
```

## bugs
