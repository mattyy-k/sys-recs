LOCAL_PATH := $(call my-dir)
include $(CLEAR_VARS)
LOCAL_MODULE := forest_fire
LOCAL_SRC_FILES := main.c
LOCAL_LDLIBS := -lEGL -lGLESv3 -llog
include $(BUILD_EXECUTABLE)
