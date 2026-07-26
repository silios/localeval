## Merge Intervals

Given an array of `intervals` where `intervals[i] = [start_i, end_i]`,
merge all overlapping intervals and return an array of the non-overlapping
intervals that cover all the intervals in the input.

The input may not be sorted. The output must be sorted by start time.

**Function signature:**
```python
def merge(intervals: list[list[int]]) -> list[list[int]]:
```

**Examples:**
```
Input: [[1,3],[2,6],[8,10],[15,18]]
Output: [[1,6],[8,10],[15,18]]
Explanation: [1,3] and [2,6] overlap → [1,6]

Input: [[1,4],[4,5]]
Output: [[1,5]]
Explanation: [1,4] and [4,5] are considered overlapping (share endpoint)

Input: [[1,4],[0,4]]
Output: [[0,4]]

Input: [[1,4],[2,3]]
Output: [[1,4]]
Explanation: [2,3] is completely inside [1,4]
```
