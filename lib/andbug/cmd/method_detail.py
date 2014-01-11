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

'implementation of the "methods-detail" command'

import andbug.command, andbug.options
from andbug import log

def show_method_access_flag(methodInfo):
    '''
    函数功能：显示方法的访问属性
    '''
      
    accessFlag = ""
    if methodInfo.public!=0:
        accessFlag += "public" + "\t"
    if methodInfo.private!=0:
        accessFlag += "private" + "\t"         
    if methodInfo.protected!=0:
        accessFlag += "protected" + "\t" 
    if methodInfo.static!=0:
        accessFlag += "static" + "\t"                 
    if methodInfo.final!=0:
        accessFlag += "final" + "\t"                
    if methodInfo.synchronized!=0:
        accessFlag += "synchronized" + "\t"                 
    if methodInfo.bridge!=0:
        accessFlag += "bridge" + "\t" 
    if methodInfo.varargs!=0:
        accessFlag += "varargs" + "\t"                 
    if methodInfo.native!=0:
        accessFlag += "native" + "\t" 
    if methodInfo.abstract!=0:
        accessFlag += "abstract" + "\t"                  
    if methodInfo.strict!=0:
        accessFlag += "strict" + "\t"
    if methodInfo.synthetic!=0:
        accessFlag += "synthetic" + "\t"
    with andbug.screed.section("ACCESS_FLAG:"):  
        if len(accessFlag) >0: 
            andbug.screed.item("%s"%(accessFlag))           


def show_method_location(methodInfo):
    '''
    函数功能：展示函数的loc和line信息
    '''
    if methodInfo.abstract!=0:
        #纯需函数，没有任何代码实现
        return
    
    lineTable=sorted(methodInfo.lineTable.iteritems(), key=lambda asd:asd[0], reverse=False)
    with andbug.screed.section("LOCATION lineTable:"):   
        for lineItem in lineTable:
            andbug.screed.item("line=%s  loc=%s" %(lineItem[0], lineItem[1].loc ))


def show_method_slot(methodInfo):
    '''
    函数功能：展示函数的参数和自变量信息
    '''
    if methodInfo.abstract!=0:
        #纯需函数，没有任何代码实现
        andbug.screed.section("ARGUMENT:") 
        andbug.screed.section("VARIABLE:")        
        return
     

    thisIndex=0
    for arg in methodInfo.slots:
        thisIndex= thisIndex+1
        if arg.name=="this":
            break
              
    thisIndex= thisIndex-1 
    with andbug.screed.section("ARGUMENT:"):  
        for i in range(thisIndex, methodInfo.slot_cnt):                
            arg = methodInfo.slots[i]
            if arg.jni[0]=='L':
                andbug.screed.item(arg.jni[1:-1]+ "  " +arg.name) 
            elif arg.jni[0]=='[':
                andbug.screed.item(show_type(arg.jni)+ "  " +arg.name)
            else:
                andbug.screed.item(andbug.vm.get_variable_type(arg.jni) + "  " +arg.name)
            
    with andbug.screed.section("VARIABLE:"):
        for i in range(0, thisIndex):                
            arg = methodInfo.slots[i]
            #print arg.jni
            if arg.jni[0]=='L':
                andbug.screed.item(arg.jni[1:-1]+ "  " +arg.name) 
            elif arg.jni[0]=='[':
                andbug.screed.item(show_type(arg.jni)+ "  " +arg.name)
            else:
                andbug.screed.item(andbug.vm.get_variable_type(arg.jni) + "  " +arg.name)
                
def show_type(jni):
    showTypeList=[]
    for item in jni:
        if item=="[":
            showTypeList.insert(0,"[]")
        else:
            showTypeList.insert(0,andbug.vm.get_variable_type(item))
    showType= ""
    for item in showTypeList:
        showType += item
    return showType
                     
@andbug.command.action('<class-path> [<method-query>]')
def method_detail(ctxt, cpath, mquery=None):
    '获取一个指定成员函数的详细信息'
    cpath, mname, mjni = andbug.options.parse_mquery(cpath, mquery)  #cpath=Lcom/example/test/MainActivity;     mname=onCreate [函数名]  mjni=None［可能是参数信息不确定］ 

  
    if mname==None:
        andbug.screed.item("please Input methods name")  
        return
    
    title = "Methods " + ((cpath + "->" + mquery) if mquery else (cpath))
    with andbug.screed.section(title):
        for m in ctxt.sess.classes(cpath).methods(name=mname, jni=mjni):
            with andbug.screed.section('Method Detail:'):
                andbug.screed.item(str(m))                  
                
            show_method_access_flag(m)            
            show_method_slot(m)
            show_method_location(m)
            
  
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                
                