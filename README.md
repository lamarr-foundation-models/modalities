# LLMgym

# Installation

Create conda environment and activate it via 
```
conda create -n llm_gym python=3.10
conda activate llm_gym
```

then, install the repository via

```
cd src
pip install -e . 
```


To run the gpt2 training

```
cd src/gpt2
torchrun --nnodes 1 --nproc_per_node 4  fsdp.py
```


VS code debugging config
```
        {
            "name": "GPT2 Example FSDP",  // accelerate launch --multi_gpu --gpu_ids "0,1,3" --num_processes=3 
            "type": "python",
            "request": "launch",
            //"module": "torchrun",
            "program": "/home/max-luebbering/miniconda3/envs/llm_gym/bin/torchrun",
            "console": "integratedTerminal",
            "env": {"CUDA_VISIBLE_DEVICES": "1,2,3,4,5,6,7"},
            "args": ["--nnodes", "1", "--nproc_per_node", "7",  "/raid/s3/opengptx/max_lue/LLMgym/src/llm_gym/fsdp.py"],
            "justMyCode": false
        }
```