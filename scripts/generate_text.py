#!/usr/bin/env python3

import argparse
import os
import sys
from collections import OrderedDict
from pathlib import Path

import torch
from torch.nn import functional as F
from transformers import GPT2TokenizerFast

from llm_gym.__main__ import load_app_config_dict
from llm_gym.config.config import AppConfig
from llm_gym.resolver_register import ResolverRegister

chat_prefix = """
This is a converstation between a user and a helpful bot, which answers the user's questsions as good as possible.

user: What is 1+1?
bot: 1+1 is 2.

user: What color is the sky?
bot: The sky is usually blue during the day.

user: How many legs does a cat have?
bot: a cat has 4 legs.

user: What is 2 - 1?
bot: 1

user: John has 3 apples. He gives Sally one apple. How many apples does Sally have?
bot: Assuming Sally did not have any apples initially, she has now exaclty one apple.

user: What is a chicken?
bot: A chicken is a domesticated bird which is keept as a source of food.

user: Count from 2 to 6
bot: 2 3 4 5 6

user: Is Pluto a planet?
bot: The International Astronomical Union (IAU) downgraded the status of Pluto to that of a
     dwarf planet because it did not meet the three criteria the IAU uses to define a full-sized planet.

user: What can you tell me about Venus?
bot: "Venus" is a roman goddess and also the name of a planet in our solar system.

user: How many oceans are there?
bot: There are five oceans - the Atlantic, Pacific, Indian, Arctic and Antarctic oceans.

"""
chat_prompt_template = """user: {prompt}
bot: """


def generate(
    model: torch.nn.Module,
    tokenizer: GPT2TokenizerFast,
    context: str,
    seq_len: int,
    max_new_tokens: int,
    temperature: float = 1.0,
):
    in_batch = tokenizer([context])
    in_batch["input_ids"] = torch.Tensor(in_batch["input_ids"]).to(torch.int64)

    for _ in range(max_new_tokens):
        in_batch["input_ids"] = (
            in_batch["input_ids"] if in_batch["input_ids"].size(1) <= seq_len else in_batch["input_ids"][:, -seq_len:]
        )
        logits = model.forward(in_batch)["logits"]
        logits = logits[:, -1, :] / temperature
        probs = F.softmax(logits, dim=-1)
        idx_next = torch.multinomial(probs, num_samples=1)
        in_batch["input_ids"] = torch.cat((in_batch["input_ids"], idx_next), dim=1)
        print(tokenizer.decode(idx_next[0]), end="")
        sys.stdout.flush()

    return in_batch["input_ids"]


if __name__ == "__main__":
    os.environ["LOCAL_RANK"] = "1"
    os.environ["RANK"] = "1"
    os.environ["WORLD_SIZE"] = "1"

    parser = argparse.ArgumentParser()
    parser.add_argument("model_path", type=str, help="path to model.bin")
    parser.add_argument("config_path", type=str, help="path to config.yaml")
    parser.add_argument("--chat", action="store_true", help="activate 'chat' mode")
    args = parser.parse_args()

    tokenizer = GPT2TokenizerFast(tokenizer_file="./data/tokenizer/tokenizer.json")
    path = Path(args.model_path)
    state_dict = torch.load(path)
    s_d = OrderedDict({(k[6:], v) for k, v in state_dict.items()})
    print(f"using {args.model_path}")

    config_dict = load_app_config_dict(args.config_path)
    config = AppConfig.model_validate(config_dict)
    resolvers = ResolverRegister(config=config)
    model: torch.nn.Module = resolvers.build_component_by_config(config=config.model)
    model.load_state_dict(state_dict)
    model.eval()

    while True:
        try:
            print("-" * 50)
            if args.chat is True:
                prompt = input("enter question> ")
                ret = generate(model, tokenizer, prompt, config.data.sequence_len, 100)
            else:
                prompt = input("enter prompt> ")
                ret = generate(model, tokenizer, prompt, config.data.sequence_len, 100)
            print("\n")
        except KeyboardInterrupt:
            print("closing app...")
            break
