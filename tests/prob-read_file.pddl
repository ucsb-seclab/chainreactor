(define (problem suid-read)
  (:domain micronix)
  (:objects
    user - user
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

    (file_owner file user group)
    (user_group user group)

    (file_present_at_location file location)
    (file_contents file data)
    
    (controlled_user user)
  )

  (:goal (user_data_in_buffer user data))
)