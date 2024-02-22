# FIXME
# def test_pretrained_gpt_model(tmp_path):
#     # setup config and model
#     attention_config = AttentionConfig(attention_type=AttentionType("default_attention"), scaling_factor=3)
#     config = GPT2LLMConfig(
#         block_size=12,
#         vocab_size=128,
#         n_layer=2,
#         n_head=2,
#         n_embd=128,
#         ffn_hidden=128,
#         dropout=0.01,
#         bias=True,
#         attention=attention_config,
#         activation=ActivationType.GELU,
#         epsilon=1e-5,
#         sample_key="input_ids",
#         prediction_key="logits",
#         weight_init=WeightInitailizationConfig(mean=0, std=0.02),
#     )
#     pretrained_config = HuggingFacePretrainedModelConfig(config=config)

#     model = HuggingFacePretrainedModel(**pretrained_config)
#     model.save_pretrained(tmp_path)
#     model = model.eval()

#     # register config and model
#     AutoConfig.register("modalities_gpt2", HuggingFacePretrainedModelConfig)
#     AutoModelForCausalLM.register(HuggingFacePretrainedModelConfig, HuggingFacePretrainedModel)

#     # load saved model
#     loaded_model = AutoModelForCausalLM.from_pretrained(tmp_path)
#     loaded_model = loaded_model.eval()

#     # check that model before and after loading return the same output
#     test_tensor = torch.randint(10, size=(5, 10))
#     output_before_loading = model.forward(test_tensor)
#     output_after_loading = loaded_model.forward(test_tensor)
#     assert (output_after_loading == output_before_loading).all()
