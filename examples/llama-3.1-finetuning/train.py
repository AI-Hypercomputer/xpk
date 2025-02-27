from datasets import load_dataset
from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments, Trainer, DataCollatorForLanguageModeling
import torch
import transformers

# 1. Data Loading and Preprocessing
dataset = load_dataset("json", data_files="training_data.jsonl", split="train")

def create_prompt(example):
    prompt_template = """<|begin_of_text|><|start_header_id|>user<|end_header_id|>
{instruction} {input}<|eot_id|><|start_header_id|>assistant<|end_header_id|>
{output}<|end_of_text|>"""
    input_text = example["input"].strip() if example["input"] else ""
    if len(input_text) > 0:
        input_text = " " + input_text
    full_prompt = prompt_template.format(
        instruction=example["instruction"].strip(),
        input=input_text,
        output=example["output"].strip()
    )
    return {"text": full_prompt}

dataset = dataset.map(create_prompt)

tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B-Instruct", trust_remote_code=True)
tokenizer.add_special_tokens({'pad_token': '<pad>'})
tokenizer.padding_side = 'right'

def tokenize_function(example):
    return tokenizer(example["text"], padding="max_length", truncation=True, max_length=512)

tokenized_dataset = dataset.map(tokenize_function, batched=True)
tokenized_dataset = tokenized_dataset.remove_columns(["text", "instruction", "input", "output"])


# 2. Model Loading
model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-3.1-8B-Instruct", trust_remote_code=True, torch_dtype=torch.bfloat16, device_map="auto")
model.resize_token_embeddings(len(tokenizer))


# 3. Training Configuration
training_args = TrainingArguments(
    output_dir="./llama3-finetuned",
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    learning_rate=2e-5,
    num_train_epochs=3,
    logging_dir="./logs",
    logging_steps=10,
    save_steps=100,
    eval_strategy="no",
    fp16=False,
    bf16=True,
    load_best_model_at_end=False,
    save_total_limit=2,
    report_to="tensorboard",
    push_to_hub=False,
)

# 4. Training Loop
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_dataset,
    data_collator=DataCollatorForLanguageModeling(tokenizer, mlm=False)
)

trainer.train()
trainer.save_model("./llama3-finetuned-final")
tokenizer.save_pretrained("./llama3-finetuned-final")

