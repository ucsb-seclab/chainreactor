(define (problem add-permission)
  (:domain micronix)
  (:objects
    alice - user
    file - file
    chmod - executable
    process - process
    data - data
    group - group
  )

  (:init
    (CAP_change_permission chmod)
    (system_executable chmod)

    (file_owner file alice group)
    (user_group alice group)

    (controlled_user alice)
  )

  (:goal (default_file_permission file FS_WRITE))
)