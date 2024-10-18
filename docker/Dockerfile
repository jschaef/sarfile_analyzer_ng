FROM registry.suse.com/suse/sle15:15.6

RUN \
        zypper --gpg-auto-import-keys ref -s &&\
        zypper up -y &&\
        zypper -n in \
                python312 \
                python312-tk \
                python3-urllib3 \
                vim \
                git-core \
                less \
                awk \
                gcc
RUN \
         zypper clean --all
COPY 	./code sarfile_analyzer_ng/code
RUN \
        cd sarfile_analyzer_ng/code &&\
        python3.12 -m venv venv &&\
        source venv/bin/activate &&\
        pip install -U pip &&\
        pip install -r requirements.txt

#ENTRYPOINT  
WORKDIR /sarfile_analyzer_ng/code
CMD ["/sarfile_analyzer_ng/code/venv/bin/streamlit",  "run", "start_sar_analyzer.py"]
