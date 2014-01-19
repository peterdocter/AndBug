andbug 
1. can't get the argument and var when the apk was processed by ProGuard tool.
    [problem]:debug the andbug program found that client sent "call jdwp 0x06 05" to get the function table information,but return
the result is that the count of arg is 1 and the count of var is zero.
	[sulution]: 
		(1).find the method of PrgGuard tool to process apk.
		(2).get dalvik machine detail for jdwp protocal.