(define (problem suid-read)
  (:domain micronix)
  (:objects
    alice bob - user
    file - file
    group - group
    directory - directory
    reader - executable
    process - process
    data - data
    location - local
  )

  (:init
    (CAP_read_file reader)
    (system_executable reader)

    (file_owner file alice group)

    (user_group alice group)
    (user_group bob group)
    
    (group_file_permission group file FS_READ)

    (file_present_at_location file location)
    (file_contents file data)
    
    (controlled_user bob)
  )

  (:goal (user_data_in_buffer bob data))
)