## Two Sum

Given an array of integers `nums` and an integer `target`, return the
indices of the two numbers such that they add up to `target`.

Your solution must run in O(n) time complexity - do not use nested loops.

**Function signature:**
```python
def two_sum(nums: list[int], target: int) -> list[int]:
```

Return a list of two indices `[i, j]` where `nums[i] + nums[j] == target`
and `i != j`. You may assume exactly one solution exists, but you must
return the indices in ascending order.

**Example:**
```
Input: nums = [2, 7, 11, 15], target = 9
Output: [0, 1]
Explanation: nums[0] + nums[1] == 9
```

Your code file must define the `two_sum` function. The verifier will
import it and run test cases.
