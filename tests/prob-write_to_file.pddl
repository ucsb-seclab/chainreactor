(define (problem write-file)
  (:domain micronix)
  (:objects
    user - user
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

    (file_owner file user group)
    (user_group user group)

    (user_data_in_buffer user data)
        
    (controlled_user user)
  )

  (:goal (file_contents file data))
)