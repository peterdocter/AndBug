#!/usr/bin/env python
# -*- coding: utf-8 -*- 

## Copyright 2011, IOActive, Inc. All rights reserved.
##
## AndBug is free software: you can redistribute it and/or modify it under 
## the terms of version 3 of the GNU Lesser General Public License as 
## published by the Free Software Foundation.
##
## AndBug is distributed in the hope that it will be useful, but WITHOUT ANY
## WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS 
## FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public License for 
## more details.
##
## You should have received a copy of the GNU Lesser General Public License
## along with AndBug.  If not, see <http://www.gnu.org/licenses/>.

'implementation of the "mtrace" command'

'''
文件功能：该模块用于对android应用实现函数粒度的监控功能
'''

import logging
import shlex
import json


import andbug.command, andbug.screed, andbug.options, andbug.vm
import andbug.config
from andbug import log



BANNER = 'AndBug (C) 2011 Scott W. Dunlop <swdunlop@gmail.com>'
'''
logFilePath = 'myapp.log'
logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                datefmt='%a, %d %b %Y %H:%M:%S',
                filename=logFilePath,
                filemode='w')
'''



def report_hit(t):
    t = t[0]
    try:
        with andbug.screed.section("trace-monitor %s" % t):
            #获取函数信息
            funInfor={}            
            f = t.frames[0]
            name = str(f.loc)
            funInfor["thread"] = str(t)
            funInfor["name"] = name
            funInfor["is_native"] = f.native
            
            with andbug.screed.item(name):
                #获取函数的参数信息
                args={}
                for k, v in f.values.items():
                    andbug.screed.item( "%s=%s" %(k, v))
                    valueType = str(type(v))
                    index = valueType.find("class")
                    if index==-1:
                        #主类型变量，int long等                       
                        args[k]=v
                    else:
                        #对象类型变量
                        pass              
                        args[k]=v.genJson()
                     
                   
         
                    
            funInfor["args"]= args    
        
            monitor_infor = json.dumps(funInfor)    
            logging.debug(monitor_infor)
            #log.debug("stdu", monitor_infor)
    finally:
        t.resume()

#cmd_hook_methods(ctxt, monitorType, cpath, mname)   
def cmd_hook_methods(ctxt, monitorType, cpath, mpath):

    classesInfor = ctxt.sess.classes(cpath)
    if len(classesInfor)==0:
        return False

    for c in classesInfor:
        print "classInfor:" + str(c)
        for m in c.methods(mpath):
            print "method:" + str(m)
            
            loc = m.firstLoc
            if loc==None:
                print "firstLoc is None"
                continue
            
            andbug.screed.item('Hooked [%s] %s'%(monitorType, loc))
            if loc.native:
                andbug.screed.item('Could not hook native %s' % loc)
                continue
            
            
            if monitorType=="in":
                loc.hook(func = report_hit)
            
            elif monitorType == "out":
                print "hook out"
                loc.hookOut(func = report_hit)
            else:
                loc.hook(func = report_hit)
                loc.hookOut(func = report_hit)
            
    return True
           
def HookGoGoGo(ctxt, hookFailedInfor):
    '''
    函数：将hook失败的函数继续进行hook
    参数：hookFailedInfor 记录hook失败的函数列表
    返回值：
    '''
    if hookFailedInfor==None:
        return False, None
    
    newHookFailedInfor=[]
    
    
    for funInfor in hookFailedInfor:
        monitorType = funInfor["monitorType"]
        cpath = funInfor["cpath"]
        mname = funInfor["mname"]
        flag=cmd_hook_methods(ctxt, monitorType, cpath, mname)  
        if flag==False:
             newHookFailedInfor.append(funInfor)
        
    if len(newHookFailedInfor)==0:
        print "hook all function"
        return True, None
    else:
        return False, newHookFailedInfor

def ParseMonitorConfItem(configInforItem):
    '''
    函数功能：用来解析一条监控配置信息
    参数：一条监控配置信息
    返回值：
    in java.io.File.<init>
    '''
    configInforItem = configInforItem.strip()
    if configInforItem==None or len(configInforItem)==0 or configInforItem[0]=='#':
        #如果是注释行或是空行，返回None
        return False, None, None, None, None
    confInfor = configInforItem.split(' ')
    monitorType = confInfor[0]
    #对于正常配置信息，返回一个list，第一个元素是中断类型（in,out,inout），第二个元素是中断函数的位置。
    cpath, mname, mjni = andbug.options.parse_mquery(".".join(confInfor[1].split('.')[0:-1]),  confInfor[1].split('.')[-1]) 
    return  True, monitorType, cpath, mname, mjni



def input():
    return raw_input('>> ')

'''    
@andbug.command.action(
    '<method>', name='monitor', aliases=('mo'), shell=True
)
'''
@andbug.command.action(
    '<method>', name='monitor', aliases=('mo',)
)
def monitor(ctxt, monitor_log_file_path="1111", monitor_file_md5="00000", task_file_path=andbug.config.g_Date_File_Path):
    '''
    函数功能：对指定的函数调用情况进行监控
    参数:    monitor_log_file_path  保存监控内容的文件路径
            monitor_file_md5       被监控apk文件的md5值
            task_file_path         监控规则配置文件
            
    '''

    logFilePath = monitor_log_file_path
    logging.basicConfig(level=logging.DEBUG,
                format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
                #datefmt='%a, %d %b %Y %H:%M:%S',
                filename=logFilePath,
                filemode='w')
    print "task_file_path:" + task_file_path
    

    file = open(task_file_path)        # 返回一个文件对象
    line = file.readline()             # 调用文件的 readline()方法
    
    unhookFunList=[]
    with andbug.screed.section('Setting Hooks'):
        while line:    
            
            flag, monitorType, cpath, mname, mjni = ParseMonitorConfItem(line)
            print "flag=%s, monitorType=%s, cpath=%s, mname=%s, mjni=%s "%(flag,monitorType, cpath, mname, mjni)
            print "line=%s"%(line)
            if flag==False:
                line = file.readline()
                continue    
            try:
                flag=cmd_hook_methods(ctxt, monitorType, cpath, mname)   
                if flag==False:
                    unhookFun = {}
                    unhookFun["monitorType"]=monitorType
                    unhookFun["cpath"]=cpath
                    unhookFun["mname"]=mname
                    unhookFunList.append(unhookFun)
                         
            except Exception:
                print "RequestError "+ cpath + "-" + mname 
                
            line = file.readline()

    file.close()
    
    #输出hook失败的函数：
    for fun in unhookFunList:
        print "unhookFun: %s/%s "%(fun["cpath"],fun["mname"])
    
    for i in range(0,5):
        flag, newUnhookFunList = HookGoGoGo(ctxt, unhookFunList)
        #print "i=%d  flag=%s len=%d"%(i, flag, len(newUnhookFunList))
        unhookFunList = newUnhookFunList
    
    andbug.screed.section('Setting Hooks sucessful')
    
    if not ctxt.shell:
        try:
            import readline
        except:
            readline = None
        ctxt.shell = True
        andbug.screed.section(BANNER)
        
    while True:
        try:
            cmd = shlex.split(input())
        except EOFError:
            return
        andbug.screed.pollcap()
        if cmd:
            andbug.command.run_command(cmd, ctxt=ctxt) #在这里接收控制台输入的命令，实现具体的调试工作。
    
