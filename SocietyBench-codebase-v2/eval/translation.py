from pprint import pprint
from transformers.image_transforms import reorder_images
from math import floor
from tarfile import TarError
from typing import Any
import json
import os
import sys
import time
from pathlib import Path
import argparse
from common import load_pipeline_config
from huggingface_hub import login

# Trns imports
import nltk
import torch
from transformers import AutoModelForSeq2SeqLM, BitsAndBytesConfig, AutoTokenizer
from IndicTransToolkit.processor import IndicProcessor
import heapq

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
import math
import traceback

import torch
from transformers import AutoModelForSeq2SeqLM, BitsAndBytesConfig, AutoTokenizer
from IndicTransToolkit.processor import IndicProcessor

from prettytable import PrettyTable

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
quantization = None


def collect_fields(data, TARGET_FIELDS):
    """
    Flatten target fields into a list of strings.
    Keep a mapping from each string to its record index and field.
    """
    strings = []
    locations = []

    for record_index, record in enumerate(data):
        if not isinstance(record, dict):
            continue

        for field in TARGET_FIELDS:
            value = record.get(field)

            if isinstance(value, str):
                strings.append(value)
                locations.append((record_index, field))

    return strings, locations

def initialize_model_and_tokenizer(ckpt_dir, quantization):
    if quantization == "4-bit":
        qconfig = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
    elif quantization == "8-bit":
        qconfig = BitsAndBytesConfig(
            load_in_8bit=True,
            bnb_8bit_use_double_quant=True,
            bnb_8bit_compute_dtype=torch.bfloat16,
        )
    else:
        qconfig = None

    tokenizer = AutoTokenizer.from_pretrained(ckpt_dir, trust_remote_code=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(
        ckpt_dir,
        trust_remote_code=True,
        low_cpu_mem_usage=True,
        quantization_config=qconfig,
    )

    if qconfig == None:
        model = model.to(DEVICE)
        if DEVICE == "cuda":
            model.half()

    model.eval()

    return model, tokenizer

def translate_this_batch(batch, ip_processor, source_lang, target_lang, tokenizer, translation_model):
    # ERR CODES : 0 - Passed, 1 - Processing Error, 2 - Attempts Exceeded,
    BATCH_NO = batch[0]
    ATTEMPT_NO = batch[1]
    if (ATTEMPT_NO <= 3):
        try:
            print(f"---"*8 + f"PROCESSING BATCH #{BATCH_NO}" + f"---"*8)
            print(f"---"*8 + f"ATTEMPT #{ATTEMPT_NO}" + f"---"*8)

            input_sentences = batch[-1]

            preprocessed_batch = preprocess_batch(input_sentences, ip_processor, source_lang, target_lang)
            tokenized_inputs = tokenize_batch(preprocessed_batch, tokenizer)
            translated_tokens = translate_batch(tokenized_inputs, translation_model)
            decoded_translation = decode_translation(translated_tokens, tokenizer)
            translations = postprocess_batch(decoded_translation, target_lang, ip_processor)


            # for input_sentence, translation in zip(input_sentences, translations):
            #     print(f"{source_lang}: {input_sentence}")
            #     print(f"{target_lang}: {translation}")

            ATTEMPT_NO += 1
            return (0, (BATCH_NO, ATTEMPT_NO, translations))

        except Exception as e:
            print(f"xxx"*8 + f"ERROR occured: {e}" + f"xxx"*8)
            print(traceback.format_exc())
            ATTEMPT_NO += 1

            if ATTEMPT_NO <= 3:
                print(f"---"*8 + f"Will be processed in attempt {ATTEMPT_NO}" + f"---"*8)

            return (1, (BATCH_NO, ATTEMPT_NO, input_sentences))

        else:
            # ATTEMPTS EXCEEDED
            return (2, batch)



def preprocess_batch(input_sentences, ip, source_lang, target_lang):

    processed_batch = ip.preprocess_batch(
        input_sentences,
        src_lang=source_lang,
        tgt_lang=target_lang,
    )

    return processed_batch

def tokenize_batch(preprocessed_batch, tokenizer):
    # Tokenize the sentences and generate input encodings
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

    inputs = tokenizer(
            preprocessed_batch,
            truncation=True,
            padding="longest",
            return_tensors="pt",
            return_attention_mask=True,
        ).to(DEVICE)

    return inputs

def translate_batch(tokenized_inputs, model):
    # Generate translations using the model

    with torch.no_grad():
        generated_tokens = model.generate(
            **tokenized_inputs,
            use_cache=True,
            min_length=0,
            max_length=256,
            num_beams=5,
            num_return_sequences=1,
        )

    return generated_tokens

def decode_translation(translated_tokens, tokenizer):
   # Decode the generated tokens into text
    decoded_translation = tokenizer.batch_decode(
        translated_tokens,
        skip_special_tokens=True,
        clean_up_tokenization_spaces=True,
    )

    return decoded_translation

def postprocess_batch(generated_tokens, tgt_lang, ip):
    translations = ip.postprocess_batch(generated_tokens, lang=tgt_lang)
    return translations


def batch_num_to_entry_index_range(batch_num, BATCH_SIZE):
    starts_from_record = (batch_num - 1) * BATCH_SIZE
    ends_at_record = starts_from_record + BATCH_SIZE # Not included when ranged

    return (starts_from_record, ends_at_record)

def entry_num_to_batch(record_num, BATCH_SIZE):
    batch_num = math.floor(record_num / BATCH_SIZE) + 1
    return batch_num


# DOES EVERYTHING IN BATCHES
def the_batcher(
    input_sentences,
    BATCH_SIZE,
    ip_processor,
    source_lang,
    target_lang,
    tokenizer,
    translation_model
):
    # Create batches
    total_batches = []
    batch_num = 0
    trans_attempt = 1

    # table = [["Batch", "Text"]]
    # tab = PrettyTable(table[0])

    for i in range(0, len(input_sentences), BATCH_SIZE):
        batch = input_sentences[i : i + BATCH_SIZE]
        batch_num += 1
        total_batches.append(
            (batch_num, trans_attempt, batch)
        )  # Structure of each batch : Batch num starts from 1, trans_attempt also from 1 and then list of sentences
        # tab.add_row([str(batch_num), str(batch)])

    # print(tab)


    heapq.heapify(total_batches)
    pending_batches = total_batches
    completed_entries = {} # {record_number : its_translation}
    completed_batches = {} # Redundant : DELETE LATER

    erred_batches = []
    erred_batch_nums = {}

    # PRINT A PRETTY TABLE : UNNECCESSARY
    # table = [["Tasks", "Count"],["Total batches",str(len(total_batches))],["Pending batches",str(len(pending_batches))]]
    # tab = PrettyTable(table[0])
    # tab.add_rows(table[1:])
    # print(tab)

    while pending_batches:
        current_batch = heapq.heappop(pending_batches)

        err_code = -1

        # Send for translation
        try:
            err_code, translated_batch = translate_this_batch(current_batch, ip_processor, source_lang, target_lang,tokenizer,translation_model)
        except Exception as e:
            print(f"Error while translating batch {current_batch[0]}")
            print(f"Error: {e}")
            print(traceback.format_exc())

            if current_batch[1] < 3:
                heapq.heappush(pending_batches,(current_batch[0], current_batch[1]+1, current_batch[-1]))

        if err_code == 0:
            batch_num = translated_batch[0]
            translated_text = translated_batch[-1]


            entry_index_range = batch_num_to_entry_index_range(batch_num, BATCH_SIZE)
            entry_starting_index = entry_index_range[0]
            entry_ending_index = entry_index_range[1]

            completed_batches[batch_num] = translated_text

            pointer = 0
            # print(len(translated_text))
            for i in range(entry_starting_index, entry_ending_index):
                # HANDLE LAST BATCH WITH < BATCH SIZE ELEMENTS IN IT
                if (i - entry_starting_index) >= len(translated_text):
                    break
                completed_entries[i] = translated_text[pointer]
                pointer += 1



        elif err_code == 1:
            heapq.heappush(pending_batches, translated_batch)
        else:
            erred_batches.append(translated_batch)
            batch_num = translated_batch[0]
            erred_batch_nums.add(batch_num)

    print("Completed_entries")
    print(completed_entries)
    return completed_entries, erred_batch_nums


def reconstruct_json(data, locations, translations, erred_batches, BATCH_SIZE):



    """Put translated strings back into their original fields."""
    entry_num = 0
    for (record_index, field), translated_value in zip(locations, translations):
        batch_num = entry_num_to_batch(entry_num, BATCH_SIZE)
        if batch_num in erred_batches:
            del data[record_index]
            continue


        data[record_index][field] = translations[entry_num]
        entry_num += 1

    return data


def main():

    p = argparse.ArgumentParser(description="translate from non english to english")
    p.add_argument("input_jsonl")
    p.add_argument("output_path")
    p.add_argument("--en-indic-chk-dir")
    p.add_argument("--model", default=None)
    p.add_argument("--pipeline-config", default=None)
    p.add_argument("--batch-size", default=5)
    args = p.parse_args()

    if len(sys.argv) not in (2, 3, 4):
        print(
            "Usage: python translate_json.py input.json [output.json] pipeline_config.json"
        )
        sys.exit(1)

    input_path = Path(args.input_jsonl)
    output_path = Path(args.output_path)

    cfg = (
        load_pipeline_config(args.pipeline_config)
        if args.pipeline_config
        else load_pipeline_config()
    )

    try:
        HF_TOKEN = cfg.get("hf_token") or os.environ.get("hf_token")
        if HF_TOKEN == "":
            raise KeyError("Missing hugging face token from either config or environment")
    except KeyError as e:
        raise KeyError(f"Environment does not contain hf_token in its path. \n\
            Missing hugging face token inside the environment \n\
                {e}")

        
    login(token=HF_TOKEN)


    en_indic_ckpt_dir = args.en_indic_chk_dir or "ai4bharat/indictrans2-indic-en-1B"
    BATCH_SIZE = args.batch_size or 5
    TARGET_FIELDS = cfg.get("target_fields_for_translation") or {"title", "text", "query"}

    src_lang = "hin_Deva"
    tar_lang = "eng_Latn"

    if input_path.resolve() == output_path.resolve():
        raise ValueError("Input and output files must be different.")

    # 1. Load the original JSON.
    with input_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise TypeError("Expected a top-level JSON array.")

    print(f"Loaded {len(data)} records.")

    # 2. Collect only the specified fields.
    strings, locations = collect_fields(data, TARGET_FIELDS)  # return => [(TEXT, (INDEX, FIELD))]

    print(f"Collected {len(strings)} fields for translation.")

    # 2.5 Initialise the model, tokenizer and processor
    model, tokenizer = initialize_model_and_tokenizer(en_indic_ckpt_dir, quantization)
    ip = IndicProcessor(inference=True)


    # 3. Translate the flattened strings in batches.
    # Give erred BATCH as well, along with err code
    translated_records, erred_batch_nums = the_batcher(strings, BATCH_SIZE, ip, src_lang, tar_lang, tokenizer, model)

    # flush the models to free the GPU memory
    del tokenizer, model

    # 4. Reconstruct the original structure.
    # Remove erred rows here after matching
    reconstructed_data = reconstruct_json(data, locations, translated_records, erred_batch_nums, BATCH_SIZE)

    # 5. Save the reconstructed JSON.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = output_path.with_name(output_path.name + ".tmp")

    try:
        with temp_path.open("w", encoding="utf-8") as file:
            json.dump(
                reconstructed_data,
                file,
                ensure_ascii=False,
                indent=2,
            )
            file.write("\n")

        # Verify that the output is valid JSON.
        with temp_path.open("r", encoding="utf-8") as file:
            json.load(file)

        temp_path.replace(output_path)

    finally:
        if temp_path.exists():
            temp_path.unlink()

    print(f"Successfully saved translated JSON: {output_path}")


if __name__ == "__main__":
    main()




"""
MEEDED::
git clone https://github.com/AI4Bharat/IndicTrans2.git
cd /content/IndicTrans2/huggingface_interface

python3 -m pip install nltk sacremoses pandas regex mock transformers==4.53.2 mosestokenizer
python3 -c "import nltk; nltk.download('punkt')"
python3 -m pip install bitsandbytes scipy accelerate datasets
python3 -m pip install sentencepiece

git clone https://github.com/VarunGumma/IndicTransToolkit.git
cd IndicTransToolkit
python -m pip install --editable ./

"""