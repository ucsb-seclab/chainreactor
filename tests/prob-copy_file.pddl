(define (problem copy-file)
  (:domain micronix)
  (:objects
    user - user
    file - file
    group - group
    reader writer - executable
    p - process
    data - data
    src dst - local
  )

  (:init
    (CAP_read_file reader)
    (CAP_write_file writer)
    (system_executable reader)
    (system_executable writer)
    
    (controlled_user user)
    (user_group user group)
    (file_owner file user group)
    (file_present_at_location file src)
  )

  (:goal (and
      (file_present_at_location file dst)
    )
  )
)
