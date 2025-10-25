# 行者 运动记录数据 下载及转换  


## 下载

```python
# 1、网页登陆行者网站，F12开发者工具 -> 网络 -> Cookie
# 2、下载所有运动记录的话设置一个较大的NUM_EXPORT，一次性获取所有运动记录;否则单独设置年份、月份、运动类型（参考网页的下拉列表）
python3 download_xingzhe_gpx.py
```


## gpx转fit

refer: https://github.com/rrym/gpx2fit/tree/master

```python
python3 gpx2fit.py
```