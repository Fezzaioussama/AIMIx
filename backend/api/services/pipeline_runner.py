def build_step_prompt(template, current_input):
    if "{input}" in template:
        return template.format(input=current_input)
    return f"{template}\n\nInput: {current_input}"


def run_pipeline_steps(pipeline, ai_service, initial_input):
    current_input = initial_input
    results = []

    for step in pipeline.steps.all():
        prompt = build_step_prompt(step.prompt, current_input)
        response = ai_service.generate_response(prompt=prompt, llm=step.model)

        results.append(
            {
                "step_order": step.order,
                "model": step.model,
                "input_used": current_input,
                "output": response,
            }
        )
        current_input = response

    return current_input, results
