from openai import OpenAI
import os

# Set API key via environment variable
API_KEY = os.getenv('OPENAI_API_KEY')

# Create client
client = OpenAI(api_key=API_KEY)

def generate_text(prompt):
    try:
        response = client.responses.create(
            model="gpt-4o",
            input=prompt
        )

        return response.output_text

    except Exception as e:
        return f"Error: {str(e)}"


if __name__ == "__main__":
    user_input = input("Enter your prompt: ")
    result = generate_text(user_input)
    print("\nResponse:\n")
    print(result)