# Style guide for documents

This guide applies to `README.md`, to the files in `docs/` and to comments in manifests. The style is based on ASD-STE100 Simplified Technical English. The goal is text that an operator can read once, at speed, under stress.

## Sentences

- Write short sentences. Use a maximum of 20 words in a procedure. Use a maximum of 25 words in a description.
- Give one instruction or one fact in each sentence.
- Use the active voice. Write "ArgoCD reverts the change", not "the change is reverted".
- Use the present tense for facts. Write "the chart renders", not "the chart will render".
- Use the imperative for instructions. Write "Run `tofu plan`", not "you should run `tofu plan`".
- Do not use a contraction. Write "do not", not "don't".
- Keep a paragraph to six sentences or fewer.

## Words

- Use one word for one thing. Do not use "host", "server" and "node" for the same machine in one document.
- Write "make sure", not "ensure".
- Write "do not", not "never" or "avoid".
- Write "if", not "in case" or "should".
- Write "can" for possibility. Do not write "may" or "might".
- Write "about", not "approximately" or "roughly".
- Write "use", not "utilize" or "leverage".
- Do not use slang, humour or metaphor in a procedure.
- Give a number as a digit. Write "3 checks", not "three checks".
- Do not stack more than three nouns. Write "the token Secret for the service account", not "the service account token Secret".

## Procedures

- Number the steps. Start each step with a verb.
- Put one action in each step. If a step has "and", split it.
- Put the condition before the instruction. Write "If CI is red, read the log", not "Read the log if CI is red".
- Put a safety note before the step it applies to, not after.
- End a procedure with the expected result when the result is not obvious.

## Safety notes

Use exactly three labels. Put the label in capitals, then a colon, then the text.

| Label | Use it when |
|---|---|
| `WARNING:` | The action can cause loss of data or loss of service. |
| `CAUTION:` | The action can cause damage that an operator can repair. |
| `NOTE:` | The reader needs a fact to do the step correctly. There is no risk. |

Give the reason in the note. Write "CAUTION: Do not edit the file on the host. The next run replaces it."

## Structure

- Start a document with one paragraph that says what the repository or the file does.
- Put a "Documents" table near the top. Link each other document in `docs/`.
- Use a table for reference data. Use a numbered list for a procedure. Use a bulleted list for facts that have no order.
- Use a code block for each command, path or error message. Do not put a command in a sentence.
- Do not describe the style of the document inside the document. Link this guide instead.

## Comments in manifests

- Give the reason, not the description. The key already says what the value is.
- Give the date when the comment records a measurement or an incident. Use the format `YYYY-MM-DD`.
- Point to the incident file when one exists.

## Incident write-ups

This section applies to repositories that have a `docs/incidents/` directory.

Each file has these headings in this order: Effect, Cause, Correction, Prevention, Evidence. Put the date, the component and the severity at the top. Name the file `YYYY-MM-DD-<short-name>.md`. If the date is not known, omit the date prefix and write "not recorded".
