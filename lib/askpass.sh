#!/bin/sh
# Hands the hat password (exported by ./hat as HAT_PASSWORD) to ssh. Never hard-code it here.
printf "%s\n" "$HAT_PASSWORD"
