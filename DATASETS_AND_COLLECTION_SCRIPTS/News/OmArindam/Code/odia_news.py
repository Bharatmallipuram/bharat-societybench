import csv
import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LIMIT = 80
FIELDS = [
    "title",
    "text",
    "date",
    "id",
    "url",
    "author",
    "source_type",
    "source",
    "scraped_at",
    "query",
]
ODIA = re.compile(r"[\u0b00-\u0b7f]")

TOPICS = {
    "indian_general_elections_2024": {
        "label": "Indian-General-Elections-2024",
        "terms": [
            "ଭାରତୀୟ ଲୋକସଭା ନିର୍ବାଚନ ୨୦୨୪",
            "ଲୋକସଭା ନିର୍ବାଚନ ୨୦୨୪ ଫଳ",
            "ଭାରତ ସାଧାରଣ ନିର୍ବାଚନ ୨୦୨୪",
            "ଲୋକସଭା ଭୋଟ ଗଣତି ୨୦୨୪",
            "ଲୋକସଭା ନିର୍ବାଚନ ଫଳାଫଳ ଓଡ଼ିଆ",
            "ଓଡ଼ିଶା ଲୋକସଭା ନିର୍ବାଚନ ୨୦୨୪",
            "ମୋଦୀ ନିର୍ବାଚନ ଫଳ ୨୦୨୪",
            "ନିର୍ବାଚନ ପ୍ରଚାର ନରେନ୍ଦ୍ର ମୋଦୀ ୨୦୨୪",
            "ବିଜେପି କଂଗ୍ରେସ ଲୋକସଭା ନିର୍ବାଚନ ୨୦୨୪",
            "ପ୍ରଥମ ପର୍ଯ୍ୟାୟ ଭୋଟ ୨୦୨୪ ନିର୍ବାଚନ",
            "ଶେଷ ପର୍ଯ୍ୟାୟ ମତଦାନ ଲୋକସଭା ୨୦୨୪",
            "ରାହୁଲ ଗାନ୍ଧୀ ନିର୍ବାଚନ ପ୍ରଚାର ୨୦୨୪",
            "ଓଡ଼ିଶା ବିଧାନସଭା ଲୋକସଭା ନିର୍ବାଚନ ଫଳ ୨୦୨୪",
            "ଲୋକସଭା ନିର୍ବାଚନ ଏକଜିଟ ପୋଲ ୨୦୨୪",
            "ଭୋଟ ଗଣତି ଆସନ ଫଳାଫଳ ୨୦୨୪",
            "ନିର୍ବାଚନ ଆୟୋଗ ମତଦାନ ୨୦୨୪",
            "ଲୋକସଭା ନିର୍ବାଚନ ଷଷ୍ଠ ପର୍ଯ୍ୟାୟ ୨୦୨୪",
            "ଲୋକସଭା ନିର୍ବାଚନ ସପ୍ତମ ପର୍ଯ୍ୟାୟ ୨୦୨୪",
        ],
        "match": r"ଲୋକସଭା|ସାଧାରଣ ନିର୍ବାଚନ|ନିର୍ବାଚନ ଫଳ|ଭୋଟ ଗଣତି|ମୋଦୀ",
    },
    "us_general_elections_2024": {
        "label": "US-General-Elections-2024",
        "terms": [
            "ଆମେରିକା ନିର୍ବାଚନ ୨୦୨୪",
            "ଆମେରିକା ରାଷ୍ଟ୍ରପତି ନିର୍ବାଚନ ୨୦୨୪",
            "ଡୋନାଲ୍ଡ ଟ୍ରମ୍ପ କମଳା ହାରିସ ନିର୍ବାଚନ",
            "ଟ୍ରମ୍ପ ନିର୍ବାଚନ ବିଜୟ ୨୦୨୪",
            "ଆମେରିକା ଭୋଟ ଗଣତି ୨୦୨୪",
            "US election 2024 Odia",
            "କମଳା ହାରିସ ନିର୍ବାଚନ ୨୦୨୪",
            "ଡୋନାଲ୍ଡ ଟ୍ରମ୍ପ ଆମେରିକା ନିର୍ବାଚନ ଓଡ଼ିଆ",
            "କମଳା ହାରିସ ନିର୍ବାଚନ ପ୍ରଚାର ଆମେରିକା",
            "ଜୋ ବାଇଡେନ ନିର୍ବାଚନ ଦୌଡ଼ରୁ ଓହରିଲେ ୨୦୨୪",
            "ଆମେରିକା ନିର୍ବାଚନ ଫଳ ଟ୍ରମ୍ପ ୨୦୨୪ ଓଡ଼ିଆ",
            "ଆମେରିକା ରାଷ୍ଟ୍ରପତି ଭୋଟ ଗଣତି ୨୦୨୪",
            "ଟ୍ରମ୍ପ ରାଲି ଆକ୍ରମଣ ଜୁଲାଇ ୨୦୨୪ ନିର୍ବାଚନ",
            "ଆମେରିକା ନିର୍ବାଚନ ଫଳ ପେନସିଲଭାନିଆ ୨୦୨୪",
            "ଆମେରିକା ନିର୍ବାଚନ ଜର୍ଜିଆ ମିଚିଗାନ ୨୦୨୪",
            "ଟ୍ରମ୍ପ ବିଜୟ ରାଷ୍ଟ୍ରପତି ନିର୍ବାଚନ ଆମେରିକା",
            "କମଳା ହାରିସ ପରାଜୟ ଆମେରିକା ୨୦୨୪",
            "ଆମେରିକା ନିର୍ବାଚନ ଭୋଟର ଟର୍ନଆଉଟ ୨୦୨୪",
            "ରିପବ୍ଲିକାନ ଡେମୋକ୍ରାଟ ନିର୍ବାଚନ ୨୦୨୪ ଆମେରିକା",
        ],
        "match": r"ଆମେରିକା|ଟ୍ରମ୍ପ|ହାରିସ|ବାଇଡେନ|ରାଷ୍ଟ୍ରପତି|ନିର୍ବାଚନ",
    },
    "russia_ukraine_war_2024": {
        "label": "Russia-Ukraine-War-2024",
        "terms": [
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ୨୦୨୪",
            "ୟୁକ୍ରେନ ଉପରେ ରୁଷ ଆକ୍ରମଣ ୨୦୨୪",
            "ପୁଟିନ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ୨୦୨୪",
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଖବର ଓଡ଼ିଆ",
            "ଜେଲେନସ୍କି ରୁଷ ଯୁଦ୍ଧ ୨୦୨୪",
            "Russia Ukraine war 2024 Odia",
            "କିଭ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଆକ୍ରମଣ",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଜାନୁଆରୀ ୨୦୨୪",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଜୁନ ୨୦୨୪",
                    "କୁର୍ସ୍କ ୟୁକ୍ରେନ ଆକ୍ରମଣ ୨୦୨୪",
                    "ରୁଷ ଡ୍ରୋନ ଆକ୍ରମଣ ୟୁକ୍ରେନ ୨୦୨୪",
                    "ୟୁକ୍ରେନ ଯୁଦ୍ଧବିରତି ଆଲୋଚନା ୨୦୨୪",
                    "ଜେଲେନସ୍କି ଶାନ୍ତି ଯୋଜନା ରୁଷ ୨୦୨୪",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଡୋନବାସ ୨୦୨୪",
                    "ୟୁକ୍ରେନ ଖାରକିଭ ଉପରେ ରୁଷ ଆକ୍ରମଣ",
                    "ପୁଟିନ ରୁଷ ସେନା ଯୁଦ୍ଧ ଖବର ୨୦୨୪",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଅକ୍ଟୋବର ନଭେମ୍ବର ୨୦୨୪",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଫେବୃଆରୀ ୨୪ ୨୦୨୪",
                    "ଆଭଦିଭକା ୟୁକ୍ରେନ ଯୁଦ୍ଧ ୨୦୨୪",
                    "ରୁଷ ମିସାଇଲ ଆକ୍ରମଣ ୟୁକ୍ରେନ ୨୦୨୪",
                    "ୟୁକ୍ରେନ ରୁଷ ସୀମା ଆକ୍ରମଣ ୨୦୨୪",
                    "ରୁଷ ୟୁକ୍ରେନ ଶାନ୍ତି ଚୁକ୍ତି ୨୦୨୪",
                    "ନାଟୋ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ସହାୟତା ୨୦୨୪",
                    "ପୁଟିନ ଯୁଦ୍ଧବିରତି ୟୁକ୍ରେନ ୨୦୨୪",
                    "ଜେଲେନସ୍କି ରୁଷ ଆକ୍ରମଣ ଡ୍ରୋନ ୨୦୨୪",
                    "ୟୁକ୍ରେନ ରୁଷ ଯୁଦ୍ଧ ଶରଣାର୍ଥୀ ୨୦୨୪",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଡୋନେସ୍କ ୨୦୨୪",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଏପ୍ରିଲ ମେ ୨୦୨୪",
                    "ଋଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ୨୦୨୪ ଓଡ଼ିଆ",
                    "ରୁଷିଆ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଖବର ୨୦୨୪",
                    "ୟୁକ୍ରେନ ଯୁଦ୍ଧ ରୁଷିଆ ଓଡ଼ିଆ ସମାଚାର",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଡ୍ରୋନ ଆକ୍ରମଣ ୨୦୨୪",
                    "ଯୁକ୍ରେନ ଯୁଦ୍ଧ ରୁଷ ସେନା ପ୍ରଗତି ୨୦୨୪",
                    "ୟୁକ୍ରେନ ରୁଷ ଯୁଦ୍ଧ ସାମରିକ ସହାୟତା ୨୦୨୪",
                    "Russia Ukraine conflict Odia news 2024",
                    "ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଫେବୃଆରୀ ୨୦୨୪ ପ୍ରମୁଖ ଖବର",
                    "ରୁଷ ୟୁକ୍ରେନ ଆକ୍ରମଣ ମେ ଜୁନ ୨୦୨୪",
                    "ଖାରକିଭ ରୁଷ ଆକ୍ରମଣ ୨୦୨୪ ଓଡ଼ିଆ",
                    "ରୁଷ କ୍ରିମିଆ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ୨୦୨୪",
                    "ପୁଟିନ ଶାନ୍ତି ପ୍ରସ୍ତାବ ୟୁକ୍ରେନ ୨୦୨୪",
                    "ୟୁକ୍ରେନ ସେନା ରୁଷ ଅଞ୍ଚଳ ଆକ୍ରମଣ ୨୦୨୪",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଖାରକିଭ ଡୋନେଟସ୍କ ଓଡ଼ିଆ",
        ],
        "match": r"ରୁଷ|ୟୁକ୍ରେନ|ପୁଟିନ|ଜେଲେନସ୍କି|କିଭ|ଖାରକିଭ|Russia|Ukraine",
    },
    "israel_gaza_war_2024": {
        "label": "Israel-Gaza-War-2024",
        "terms": [
            "ଇସ୍ରାଏଲ ଗାଜା ଯୁଦ୍ଧ ୨୦୨୪",
            "ଗାଜା ହମାସ ଯୁଦ୍ଧ ଓଡ଼ିଆ",
            "ଇସ୍ରାଏଲ ପାଲେଷ୍ଟାଇନ ସଂଘର୍ଷ ୨୦୨୪",
            "ଗାଜାରେ ଇସ୍ରାଏଲ ଆକ୍ରମଣ ୨୦୨୪",
            "ରାଫା ଗାଜା ଆକ୍ରମଣ ଓଡ଼ିଆ",
            "ଇସ୍ରାଏଲ ହମାସ ଯୁଦ୍ଧ ୨୦୨୪",
            "Israel Gaza war 2024 Odia",
            "ଗାଜା ଯୁଦ୍ଧ ବିରତି ୨୦୨୪",
            "ଗାଜା ଯୁଦ୍ଧ ଜାନୁଆରୀ ୨୦୨୪ ଇସ୍ରାଏଲ",
            "ଇସ୍ରାଏଲ ଗାଜା ଯୁଦ୍ଧବିରତି ଚୁକ୍ତି ୨୦୨୪",
            "ରାଫା ଶରଣାର୍ଥୀ ଶିବିର ଉପରେ ଆକ୍ରମଣ ୨୦୨୪",
            "ହମାସ ବନ୍ଧକ ମୁକ୍ତ ଇସ୍ରାଏଲ ୨୦୨୪",
            "ଗାଜାରେ ମାନବିକ ସହାୟତା ଇସ୍ରାଏଲ ୨୦୨୪",
            "ନେତନ୍ୟାହୁ ଗାଜା ଯୁଦ୍ଧ ୨୦୨୪ ଓଡ଼ିଆ",
            "ଗାଜା ହସ୍ପିଟାଲ ଇସ୍ରାଏଲ ଆକ୍ରମଣ ୨୦୨୪",
            "ଇସ୍ରାଏଲ ଲେବାନନ ହିଜବୁଲ୍ଲା ଯୁଦ୍ଧ ୨୦୨୪",
            "ଗାଜା ଯୁଦ୍ଧ ଜୁଲାଇ ଅଗଷ୍ଟ ୨୦୨୪",
            "ଗାଜା ଯୁଦ୍ଧ ମାର୍ଚ୍ଚ ଏପ୍ରିଲ ୨୦୨୪",
            "ଇସ୍ରାଏଲ ଗାଜା ବନ୍ଧକ ଆଲୋଚନା ୨୦୨୪",
            "ଗାଜାରେ ଜାତିସଂଘ ଯୁଦ୍ଧବିରତି ପ୍ରସ୍ତାବ ୨୦୨୪",
            "ଇସ୍ରାଏଲ ଆକ୍ରମଣ ଖାଦ୍ୟ ସହାୟତା ଗାଜା ୨୦୨୪",
            "ହମାସ ଇସ୍ରାଏଲ ବନ୍ଧକ ମୁକ୍ତି ଚୁକ୍ତି ୨୦୨୪",
            "ନେତନ୍ୟାହୁ ରାଫା ଆକ୍ରମଣ ୨୦୨୪",
            "ଗାଜା ଯୁଦ୍ଧ ଇରାନ ଇସ୍ରାଏଲ ୨୦୨୪",
            "ଇସ୍ରାଏଲ ଗାଜା ହସ୍ପିଟାଲ ଆକ୍ରମଣ ଓଡ଼ିଆ",
            "ଋଷ ଇସ୍ରାଏଲ ଗାଜା ଯୁଦ୍ଧ ଖବର ୨୦୨୪",
            "ପାଲେଷ୍ଟାଇନ ହମାସ ଇସ୍ରାଏଲ ସଂଘର୍ଷ ଓଡ଼ିଆ",
            "ଗାଜା ଉପତ୍ୟକାରେ ଇସ୍ରାଏଲୀ ସେନା ଅଭିଯାନ ୨୦୨୪",
            "ଇସ୍ରାଏଲ ପାଲେଷ୍ଟାଇନ ଯୁଦ୍ଧବିରତି ଓଡ଼ିଆ ୨୦୨୪",
            "ଗାଜା ଯୁଦ୍ଧରେ ମୃତ୍ୟୁ ସଂଖ୍ୟା ୨୦୨୪ ଇସ୍ରାଏଲ",
            "ହମାସ ନେତା ହତ୍ୟା ଇସ୍ରାଏଲ ୨୦୨୪ ଗାଜା",
            "ଇସ୍ରାଏଲ ଗାଜା ରାହାତ ସାମଗ୍ରୀ ଆକ୍ରମଣ ଓଡ଼ିଆ",
            "ଗାଜା ଯୁଦ୍ଧ ୨୦୨୪ ବିଶ୍ୱ ଖବର ଓଡ଼ିଆ",
            "ଇସ୍ରାଏଲ ଗାଜା ଯୁଦ୍ଧ ଜୁନ ୨୦୨୪ ଖବର",
            "ଗାଜା ଶରଣାର୍ଥୀ ଇସ୍ରାଏଲ ଆକ୍ରମଣ ୨୦୨୪",
            "ହମାସ ଇସ୍ରାଏଲ ଯୁଦ୍ଧବିରତି ଆଲୋଚନା ଓଡ଼ିଆ",
            "ଇସ୍ରାଏଲ ଗାଜା ଯୁଦ୍ଧ ଅକ୍ଟୋବର ୨୦୨୪",
            "ଗାଜା ରାଫା ଆକ୍ରମଣ ଇସ୍ରାଏଲ ଓଡ଼ିଆ ଖବର",
            "ହମାସ ବନ୍ଧକ ଇସ୍ରାଏଲ ଗାଜା ୨୦୨୪",
            "ଇସ୍ରାଏଲ ପାଲେଷ୍ଟାଇନ ସଂଘର୍ଷ ତାଜା ୨୦୨୪",
        ],
        "match": r"ଗାଜା|ହମାସ|ଇସ୍ରାଏଲ|ପାଲେଷ୍ଟାଇନ|ରାଫା|Israel|Gaza|Hamas",
    },
    "icc_t20_world_cup_2024": {
        "label": "ICC-T20-World-Cup-2024",
        "terms": [
            "ଆଇସିସି ଟି୨୦ ବିଶ୍ୱକପ ୨୦୨୪",
            "ଟି୨୦ ବିଶ୍ୱକପ ଭାରତ ଓଡ଼ିଆ",
            "ଭାରତ ଦକ୍ଷିଣ ଆଫ୍ରିକା ଫାଇନାଲ ୨୦୨୪",
            "ଟି୨୦ ବିଶ୍ୱକପ ଫାଇନାଲ ଭାରତ ବିଜୟ",
            "ରୋହିତ ଶର୍ମା ଟି୨୦ ବିଶ୍ୱକପ",
            "ବିରାଟ କୋହଲି ବିଶ୍ୱକପ ୨୦୨୪",
            "T20 World Cup 2024 Odia cricket",
                    "ଆଫଗାନିସ୍ତାନ ଟି୨୦ ବିଶ୍ୱକପ ସେମିଫାଇନାଲ ୨୦୨୪",
                    "ଅଷ୍ଟ୍ରେଲିଆ ଟି୨୦ ବିଶ୍ୱକପ ବିଦାୟ ୨୦୨୪",
                    "ଭାରତ ପାକିସ୍ତାନ ଟି୨୦ ବିଶ୍ୱକପ ମ୍ୟାଚ ୨୦୨୪",
                    "ଟି୨୦ ବିଶ୍ୱକପ ସୁପର ୮ ଭାରତ ୨୦୨୪",
                    "ବାର୍ବାଡୋସ ଫାଇନାଲ ଟି୨୦ ବିଶ୍ୱକପ ୨୦୨୪",
                    "ଟି୨୦ ବିଶ୍ୱକପ ଭାରତ ବିଜୟ ରୋହିତ ଶର୍ମା",
                    "ବୁମରା ଟି୨୦ ବିଶ୍ୱକପ ପ୍ଲେୟର ଅଫ ଦ ଟୁର୍ଣ୍ଣାମେଣ୍ଟ",
                    "ବିରାଟ କୋହଲି ଟି୨୦ ବିଶ୍ୱକପ ଫାଇନାଲ ୨୦୨୪",
        ],
        "match": r"ଟି.?୨୦|ଟି.?20|ବିଶ୍ୱକପ|ବିଶ୍ୱ କପ|କ୍ରିକେଟ|ରୋହିତ|କୋହଲି|ବୁମରା",
    },
    "paris_olympics_2024": {
        "label": "Paris-Olympics-2024",
        "terms": [
            "ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ ୨୦୨୪ ଓଡ଼ିଆ",
            "ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ ଭାରତ ପଦକ",
            "ମନୁ ଭାକର ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ",
            "ନୀରଜ ଚୋପ୍ରା ଅଲିମ୍ପିକ୍ସ ୨୦୨୪",
            "ଭାରତୀୟ ହକି ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ",
            "Paris Olympics 2024 Odia India",
            "ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ ପଦକ ତାଲିକା",
                    "ସରବଜୋତ ସିଂହ ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ ୨୦୨୪",
                    "ସ୍ୱପ୍ନିଲ କୁସାଲେ ଅଲିମ୍ପିକ୍ସ ବ୍ରୋଞ୍ଜ ୨୦୨୪",
                    "ଭାରତ ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ ହକି ବ୍ରୋଞ୍ଜ",
                    "ଭିନେଶ ଫୋଗାଟ ଅଲିମ୍ପିକ୍ସ ୨୦୨୪ ଖବର",
                    "ଅମନ ସେହରାୱତ ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ ପଦକ",
                    "ଲକ୍ଷ୍ୟ ସେନ ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ ବ୍ୟାଡମିଣ୍ଟନ",
                    "ଭାରତ ପ୍ୟାରିସ ଅଲିମ୍ପିକ୍ସ ପଦକ ଗଣନା ୨୦୨୪",
                    "ମନୁ ଭାକର ଦୁଇଟି ପଦକ ଅଲିମ୍ପିକ୍ସ ୨୦୨୪",
        ],
        "match": r"ପ୍ୟାରିସ|ଅଲିମ୍ପିକ|ମନୁ ଭାକର|ନୀରଜ ଚୋପ୍ରା|ହକି|Paris|Olympic",
    },
    "neet_paper_leak": {
        "label": "NEET-Paper-Leak-current",
        "terms": [
            "ନିଟ ପେପର ଲିକ ୨୦୨୪ ଓଡ଼ିଆ",
            "NEET UG ପେପର ଲିକ ଓଡ଼ିଆ",
            "ନିଟ ପ୍ରଶ୍ନପତ୍ର ଲିକ ସିବିଆଇ",
            "ନିଟ ପେପର ଲିକ ସୁପ୍ରିମକୋର୍ଟ",
            "ନିଟ ପରୀକ୍ଷା ବିବାଦ ୨୦୨୪",
            "NEET paper leak Odia news",
            "ନିଟ ଲିକ ମାମଲା ଅଭିଯୁକ୍ତ",
            "ନିଟ ପେପର ଲିକ ଚାର୍ଜସିଟ",
                    "ନିଟ ପୁନଃ ପରୀକ୍ଷା ୨୦୨୪ ଲିକ ଓଡ଼ିଆ",
                    "ନିଟ କାଉନସେଲିଂ ସୁପ୍ରିମକୋର୍ଟ ୨୦୨୪",
                    "ନିଟ ପେପର ଲିକ ହଜାରିବାଗ ୨୦୨୪",
                    "ନିଟ ପେପର ଲିକ ପାଟନା ସିବିଆଇ",
                    "ନିଟ ମାମଲା ପ୍ରଶ୍ନପତ୍ର ଲିକ ଏନଟିଏ",
                    "ନିଟ ପରୀକ୍ଷା ଫଳ ଗ୍ରେସ ମାର୍କ ୨୦୨୪",
                    "ନିଟ ପେପର ଲିକ ଅଭିଯୁକ୍ତ ଗିରଫ ୨୦୨୪",
                    "ନିଟ ପେପର ଲିକ ସୁପ୍ରିମକୋର୍ଟ ରାୟ",
        ],
        "match": r"NEET|ନିଟ",
        "context": r"ଲିକ|ପେପର|ପ୍ରଶ୍ନପତ୍ର|ବିବାଦ|ସିବିଆଇ|CBI|ସୁପ୍ରିମ|ରଦ୍ଦ|ଚାର୍ଜସିଟ",
    },
    "asian_games": {
        "label": "Asian-Games-2026",
        "terms": [
            "ଏସୀୟ କ୍ରୀଡ଼ା ୨୦୨୬ ଓଡ଼ିଆ",
            "ଏସିଆନ ଗେମ୍ସ ୨୦୨୬ ଭାରତ",
            "ଏସୀୟ କ୍ରୀଡ଼ା ପଦକ ତାଲିକା ୨୦୨୬",
            "ଭାରତ ଏସିଆନ ଗେମ୍ସ ସ୍ୱର୍ଣ୍ଣ",
            "Asian Games 2026 Odia",
            "ଏସୀୟ କ୍ରୀଡ଼ା ହକି ଭାରତ",
            "ଏସିଆନ ଗେମ୍ସ କ୍ରିକେଟ ଫାଇନାଲ",
        ],
        "match": r"ଏସୀୟ|ଏସିଆନ|Asian Games|ପଦକ|ସ୍ୱର୍ଣ୍ଣ|ହକି|କ୍ରିକେଟ",
    },
    "russia_ukraine_war_current": {
        "label": "Russia-Ukraine-current",
        "terms": [
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ତାଜା ଖବର ଓଡ଼ିଆ",
            "ୟୁକ୍ରେନ ରୁଷ ଆକ୍ରମଣ ଖବର",
            "ପୁଟିନ ଜେଲେନସ୍କି ଯୁଦ୍ଧ ଖବର",
            "ରୁଷ ୟୁକ୍ରେନ ଶାନ୍ତି ଆଲୋଚନା",
            "Ukraine Russia latest war Odia",
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଆଜିର ଖବର ଓଡ଼ିଆ",
            "ୟୁକ୍ରେନ ଡ୍ରୋନ ରୁଷ ଆକ୍ରମଣ ତାଜା ଖବର",
            "ପୁଟିନ ଟ୍ରମ୍ପ ଶାନ୍ତି ଆଲୋଚନା ୟୁକ୍ରେନ",
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ନୂଆ ଅପଡେଟ",
            "ୟୁକ୍ରେନ ରୁଷ ଆକ୍ରମଣ ଅକ୍ଟୋବର ୨୦୨୬",
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ତାଜା ଅପଡେଟ ଆଜି",
            "ୟୁକ୍ରେନ ଡ୍ରୋନ ଆକ୍ରମଣ ରୁଷ ତାଜା ଖବର ଓଡ଼ିଆ",
            "ପୁଟିନ ଜେଲେନସ୍କି ଯୁଦ୍ଧ ଅପଡେଟ ୨୦୨୬",
            "ରୁଷ ଆକ୍ରମଣ ୟୁକ୍ରେନ ଆଜି ଖବର",
            "ୟୁକ୍ରେନ ଶାନ୍ତି ଚୁକ୍ତି ଆଲୋଚନା ୨୦୨୬",
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଡ୍ରୋନ ମିସାଇଲ ଆକ୍ରମଣ",
            "Russia Ukraine war latest Odia news 2026",
            "ରୁଷ ୟୁକ୍ରେନ ମୋର୍ଚ୍ଚା ଯୁଦ୍ଧ ତାଜା ସମାଚାର",
            "ଋଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ତାଜା ଖବର ଓଡ଼ିଆ",
            "ରୁଷିଆ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଲାଇଭ ଅପଡେଟ",
            "ଜେଲେନସ୍କି ପୁଟିନ ଯୁଦ୍ଧ ଆଲୋଚନା ତାଜା ଖବର",
            "ୟୁକ୍ରେନ ଯୁଦ୍ଧ ରୁଷ ଡ୍ରୋନ ଆକ୍ରମଣ ଆଜି",
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ସମ୍ପ୍ରତି ଘଟଣା ଓଡ଼ିଆ",
            "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଶାନ୍ତି ଚୁକ୍ତି ତାଜା",
            "ୟୁକ୍ରେନ ଯୁଦ୍ଧରେ ପୁଟିନ ନୂଆ ଘୋଷଣା ଓଡ଼ିଆ",
            "ରୁଷ ୟୁକ୍ରେନ ସୀମା ଡ୍ରୋନ ଆକ୍ରମଣ ଖବର",
            "ଜେଲେନସ୍କି ଯୁଦ୍ଧବିରତି ପ୍ରସ୍ତାବ ରୁଷ ଓଡ଼ିଆ",
            "ୟୁକ୍ରେନ ରୁଷ ସାମରିକ ଅପଡେଟ ୨୦୨୬",
            "ଋଷ ୟୁକ୍ରେନ ସଂଘର୍ଷ ଓଡ଼ିଆ",
            "ରୁଷିଆ ୟୁକ୍ରେନ ଖବର ଆଜି",
            "ୟୁକ୍ରେନ ଯୁଦ୍ଧ ପୁଟିନ ଟ୍ରମ୍ପ",
            "Russian strike Ukraine Odia",
            "Kyiv Russia attack Odia",
            "Ukraine drone Russia Odia",
            "ୟୁକ୍ରେନ ସୀମା ରୁଷ ଆକ୍ରମଣ",
            "ରୁଷ ସେନା ୟୁକ୍ରେନ ଯୁଦ୍ଧ ୨୦୨୬",
            "ଜେଲେନସ୍କି ଯୁଦ୍ଧ ଶାନ୍ତି ଓଡ଼ିଆ",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ଆଜିର ଖବର ଓଡ଼ିଆ",
                    "ୟୁକ୍ରେନ ଡ୍ରୋନ ରୁଷ ଆକ୍ରମଣ ତାଜା ଖବର",
                    "ପୁଟିନ ଟ୍ରମ୍ପ ଶାନ୍ତି ଆଲୋଚନା ୟୁକ୍ରେନ",
                    "ରୁଷ ୟୁକ୍ରେନ ଯୁଦ୍ଧ ନୂଆ ଅପଡେଟ",
                    "ୟୁକ୍ରେନ ରୁଷ ଆକ୍ରମଣ ଅକ୍ଟୋବର ୨୦୨୬",
        ],
        "match": r"ରୁଷ|ୟୁକ୍ରେନ|ପୁଟିନ|ଜେଲେନସ୍କି|Russia|Ukraine",
    },
}


def rss_items(term: str, first: int) -> list[ET.Element]:
    query = urllib.parse.quote(term)
    url = (
        "https://www.bing.com/news/search?q="
        f"{query}&format=rss&setlang=or-IN&first={first}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            root = ET.fromstring(response.read())
        return root.findall("./channel/item")
    except (urllib.error.URLError, ET.ParseError, TimeoutError):
        return []


def item_value(item: ET.Element, name: str) -> str:
    node = item.find(name)
    return (node.text or "").strip() if node is not None else ""


def canonical_url(link: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    return urllib.parse.unquote(query.get("url", [link])[0]).strip()


def source_name(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    names = {
        "sambad.in": "Sambad",
        "kanaknews.com": "Kanak News",
        "odishabhaskar.com": "Odisha Bhaskar",
        "odishatv.in": "OTV",
        "www.prameyanews.com": "Prameya",
        "www.dharitri.com": "Dharitri",
        "navbharattimes.indiatimes.com": "Navbharat Times",
        "www.abplive.com": "ABP News",
        "www.jagran.com": "Dainik Jagran",
        "www.aajtak.in": "Aaj Tak",
        "zeenews.india.com": "Zee News",
        "hindi.news18.com": "News18 Hindi",
        "www.news18.com": "News18",
    }
    return names.get(host, host)


def collect(topic: str, settings: dict) -> tuple[int, int]:
    path = ROOT / f"{topic}.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        existing = list(csv.DictReader(handle))
    existing_news = sum(row.get("source_type") == "news_article" for row in existing)
    if existing_news >= LIMIT:
        return 0, len(existing)

    seen = {row["url"] for row in existing if row.get("url")}
    additions = []
    scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for term in settings["terms"]:
        for first in range(1, 310, 12):
            if existing_news + len(additions) >= LIMIT:
                break
            for item in rss_items(term, first):
                if existing_news + len(additions) >= LIMIT:
                    break
                title = item_value(item, "title")
                description = item_value(item, "description")
                combined = f"{title} {description}"
                if not ODIA.search(title) or not re.search(settings["match"], combined, re.I):
                    continue
                if settings.get("context") and not re.search(settings["context"], combined, re.I):
                    continue
                url = canonical_url(item_value(item, "link"))
                if not url.startswith("http") or url in seen:
                    continue
                seen.add(url)
                description = description if ODIA.search(description) else title
                try:
                    published = parsedate_to_datetime(item_value(item, "pubDate"))
                    date = published.isoformat(timespec="seconds")
                except (TypeError, ValueError, OverflowError):
                    continue
                numeric_id = re.search(r"(\d{5,})(?:\.html|\.cms)?(?:\?.*)?$", url)
                article_id = (
                    f"{source_name(url).replace(' ', '').lower()}-{numeric_id.group(1)}"
                    if numeric_id
                    else hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
                )
                additions.append(
                    {
                        "title": title,
                        "text": description[:1000],
                        "date": date,
                        "id": article_id,
                        "url": url,
                        "author": "",
                        "source_type": "news_article",
                        "source": source_name(url),
                        "scraped_at": scraped_at,
                        "query": settings["label"],
                    }
                )
        if existing_news + len(additions) >= LIMIT:
            break

    if additions:
        with path.open("a", encoding="utf-8-sig", newline="") as handle:
            csv.DictWriter(handle, fieldnames=FIELDS).writerows(additions)
    return len(additions), len(existing) + len(additions)


if __name__ == "__main__":
    for topic, settings in TOPICS.items():
        added, total = collect(topic, settings)
        print(f"{topic}: added={added}, total={total}")
