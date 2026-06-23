# NOP Agent

The NOP Agent, or No Operation Agent, performs no work.

It is a lower-bound baseline used to validate that the evaluation pipeline is wired correctly and that the task is not already solved.

## Behavior

The NOP Agent:

- does not install dependencies
- does not initialize the environment
- does not process the instruction
- does not execute task logic
- immediately runs the verifier

## Expected Result

NOP should fail every real task.

If NOP passes, the task definition or verifier is likely wrong.

Common reasons NOP passes:

- task starts already solved
- tests are too weak
- verifier checks only file existence or format
- reward logic is broken
- tests are not actually running

NOP passing is a serious signal to fix the task before submission.
