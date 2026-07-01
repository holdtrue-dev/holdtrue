# Intent: clock

Do a little wall-clock arithmetic on a 24-hour day, all in whole seconds.

- **to seconds**: turn an hour, minute, and second into the number of seconds since midnight. Hours run 0 to 23, minutes and seconds 0 to 59.
- **add seconds**: add a number of seconds (which may be negative) to a time of day, wrapping around midnight so the result is always another time of day, from 0 up to but not including a full day.
- **is am**: whether a time of day falls in the morning, that is, before noon.
- **minutes between**: the whole minutes you wait going forward from one time of day to another, wrapping past midnight if the second time is earlier.

A time of day is a whole number of seconds from 0 to 86399. Four functions in all.
