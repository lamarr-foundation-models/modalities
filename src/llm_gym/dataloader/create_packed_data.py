import pickle
from pathlib import Path
from typing import IO

import jq
import numpy as np
from tqdm import tqdm
from transformers import PreTrainedTokenizer

from llm_gym.dataloader.large_file_lines_reader import LargeFileLinesReader


class PackedDataGenerator:
    def __init__(
        self,
        src_path: Path,
        tokenizer: PreTrainedTokenizer,
        index_path: Path = None,
        jq_pattern: str = ".text",
        max_number_of_tokens: int = None,
        size_in_bytes: int = 4,
        header_size_in_bytes: int = 8,
    ):
        """
        Reads in a jsonl file and the corresponding index file and packs dataset file for LLM training.
        :param src_path: Path to a jsonl file, which holds text data
        :param index_path: Path to an index file, which indicates the start character position
                           and length of samples given in `src_path`.
                           If not defined, an index file next to `src_path` is picked,
                           by replacing its suffix with ".idx".
        :param tokenizer: PretrainedTokenizer object, which is used to pre-tokenize the provided data in `src_path`.
                          Tokenization is necessary to work on final lengths of token sequences.
        :param jq_pattern: jq-pattern applied on every jsonl-entry. Results are afterwards tokenized and packed
        :param max_number_of_tokens: Limit the total amount of tokens in the packed dataset.
                                     If not specified, the whole data is packed into the dataset.
        :param size_in_bytes: amount of bytes to represent tokens as integers.
                              If the vocabulary exceeds 2^`size_in_bytes`, this requires adaptation.
        :param header_size_in_bytes: amount of bytes to represent number of all tokens in dataset.
                                     If the amount exceeds 2^`header_size_in_bytes`, this requires adaptation.
        """
        self.src_path = src_path
        self.tokenizer = tokenizer
        self.jq_filter = jq.compile(jq_pattern)
        self.max_tokens = max_number_of_tokens
        self.size_in_bytes = size_in_bytes
        self.header_size_in_bytes = header_size_in_bytes

        self._reader = LargeFileLinesReader(src_path, index_path=index_path)
        self._total_num_of_tokens = 0
        self._curr_offset = self.header_size_in_bytes
        self._index_list = []

    def _default_destination_path(self, destination_path: Path = None) -> Path:
        if destination_path is None:
            default_destination_path = Path(self.src_path.parent, f"{self.src_path.stem}.pbin")
            print(
                f"No specific Destination Path provided. "
                f"Pointing to destination next to input data at: {default_destination_path}"
            )
            return default_destination_path
        return Path(destination_path)

    def run(self, dst_path: Path = None):
        assert self._total_num_of_tokens == 0, f"This {self.__name__} was already used and is exhausted. Use another!"
        dst_path = self._default_destination_path(destination_path=dst_path)

        if dst_path.exists():
            raise ValueError(f"file already exists at destination path '{dst_path}'.")

        encoded_eos_token = self.tokenizer(self.tokenizer.eos_token)["input_ids"][0]
        encoded_eos_token_as_bytes = encoded_eos_token.to_bytes(self.size_in_bytes, byteorder="big")
        with dst_path.open("wb") as f:
            # allocate first self.header_size_in_bytes bytes for header (encodes length of data section)
            # not possible to prepend header after determining size of data section
            f.write((0).to_bytes(self.header_size_in_bytes, byteorder="big"))

            # write data section (tokens)
            for line in tqdm(self._reader):
                try:
                    self._process_line(encoded_eos_token_as_bytes, f, line)
                except StopIteration:
                    break
                except Exception as e:
                    print(f"could not process line: {e=}")

            # write index
            f.write(pickle.dumps(self._index_list))

        self._update_data_length_in_pre_allocated_header(dst_path)

    def _update_data_length_in_pre_allocated_header(self, dst_path: Path):
        start_of_index_in_bytes = self._index_list[-1][0] + self._index_list[-1][1]
        length_of_byte_encoded_data_section = start_of_index_in_bytes - self.header_size_in_bytes
        header_content = length_of_byte_encoded_data_section.to_bytes(self.header_size_in_bytes, byteorder="big")
        header_content = np.frombuffer(header_content, dtype="uint8")
        # write the header content to the packed dataset file
        m = np.memmap(dst_path, mode="r+", offset=0, shape=(self.header_size_in_bytes,))
        m[:] = header_content[:]

    def _process_line(self, eos_token_as_bytes: bytes, f: IO, line: str):
        jq_retrieved_text = self.jq_filter.input_text(line).first()
        tokens = self.tokenizer(jq_retrieved_text)["input_ids"]
        if len(tokens) == 0:
            return
        token_idx = 0
        for token in tokens:
            token_as_bytes = token.to_bytes(self.size_in_bytes, byteorder="big")
            f.write(token_as_bytes)
            self._total_num_of_tokens += 1
            if self._total_num_of_tokens == self.max_tokens:
                segment_length = (token_idx + 1) * self.size_in_bytes
                self._index_list.append((self._curr_offset, segment_length))
                raise StopIteration
            token_idx += 1
        f.write(eos_token_as_bytes)
        token_idx += 1
        segment_length = (token_idx + 1) * self.size_in_bytes
        self._index_list.append((self._curr_offset, segment_length))
        self._curr_offset += segment_length
