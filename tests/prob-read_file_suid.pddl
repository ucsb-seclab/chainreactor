(define (problem suid-read)
  (:domain micronix)
  (:objects
    alice bob - user
    flag - file
    g1 g2 - group
    directory - directory
    loader reader writer chmod - executable
    process - process
    data - data
    location - local
  )

  (:init
    (CAP_read_file reader)
    (CAP_write_file writer)
    (CAP_change_permission chmod)
    (system_executable reader)
    (system_executable writer)
    (system_executable chmod)
    (executable_does_not_drop_privileges chmod)
    (executable_does_not_drop_privileges reader)
    ; first way, change permissions
    (suid_executable chmod)
    ; or read directly
    (suid_executable reader)
    (file_owner chmod alice g1)
    (file_owner reader alice g1)
    (file_owner flag alice g1)

    (user_group alice g1)
    (user_group bob g2)
    
    (file_present_at_location flag location)
    (file_contents flag data)

    (controlled_user bob)
  )

  (:goal (user_data_in_buffer bob data))
)