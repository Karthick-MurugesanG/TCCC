# import pandasai as pai
# from pandasai_litellm.litellm import LiteLLM

# # Initialize LiteLLM with your OpenAI model
# llm = LiteLLM(model="gpt-4.1-mini", api_key="sk-438e3354720440dbb8268f3e65963c4b")

# # Configure PandasAI to use this LLM
# pai.config.set({
#     "llm": llm
# })

# employees_data = {
#     'EmployeeID': [1, 2, 3, 4, 5],
#     'Name': ['John', 'Emma', 'Liam', 'Olivia', 'William'],
#     'Department': ['HR', 'Sales', 'IT', 'Marketing', 'Finance']
# }

# salaries_data = {
#     'EmployeeID': [1, 2, 3, 4, 5],
#     'Salary': [5000, 6000, 4500, 7000, 5500]
# }

# employees_df = pai.DataFrame(employees_data)
# salaries_df = pai.DataFrame(salaries_data)


# pai.chat("Who gets paid the most?", employees_df, salaries_df)


import pandas as pd
import bambooai as bam

employees_data = {
    'EmployeeID': [1, 2, 3, 4, 5],
    'Name': ['John', 'Emma', 'Liam', 'Olivia', 'William'],
    'Department': ['HR', 'Sales', 'IT', 'Marketing', 'Finance']
}

salaries_data = {
    'EmployeeID': [1, 2, 3, 4, 5],
    'Salary': [5000, 6000, 4500, 7000, 5500]
}

employees_df = pd.DataFrame(employees_data)
salaries_df = pd.DataFrame(salaries_data)

df = pd.merge(employees_df, salaries_df, on="EmployeeID")

bamboo = bam.BambooAI()

response = bamboo.pd_agent_converse(
    df,
    "Who gets paid the most?"
)

print(response)