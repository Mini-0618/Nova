def avg(nums):
    if not nums:
        return 0
    return sum(nums) / len(nums)

if __name__ == '__main__':
    assert avg([1, 2, 3]) == 2.0
    assert avg([]) == 0, 'Empty list should return 0'
    print('PASS')