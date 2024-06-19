(define (problem suid-write)
  (:domain micronix)
  (:objects
    alice bob - user
    sensitive_file - file
    g1 g2 - group
    directory - directory
    writer - executable
    process - process
    data payload - data
    location - local
  )

  (:init
    (CAP_write_file writer)
    (system_executable writer)
    (suid_executable writer)
    (executable_does_not_drop_privileges writer)
    (file_owner writer alice g1)

    (file_owner sensitive_file alice g1)
    (file_present_at_location sensitive_file location)
    (file_contents sensitive_file data)

    ; TODO: relax this, remove
    (user_group alice g1)
    (user_group bob g2)
  
    (controlled_user bob)
    (user_data_in_buffer bob payload)
  )

  (:goal (file_contents sensitive_file payload))
)