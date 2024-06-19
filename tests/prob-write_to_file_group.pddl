(define (problem write-file-group)
  (:domain micronix)
  (:objects
    alice bob - user
    file - file
    group - group
    directory - directory
    writer - executable
    process - process
    data - data
    location - local
  )

  (:init
    (CAP_write_file writer)
    (system_executable writer)

    (file_owner file alice group)
    (user_group alice group)
    (user_group bob group)

    (group_file_permission group file FS_WRITE)

    (user_data_in_buffer bob data)
    
    (controlled_user bob)
  )

  (:goal (file_contents file data))
)