# -*- coding: utf-8 -*-
from ..describe import Description, autoDescribeRoute
from ..rest import Resource, filtermodel
from girder.api import access
from girder.constants import AccessType
from girder.exceptions import AccessException, ValidationException
from girder.models.group import Group as GroupModel
from girder.models.protoUser import ProtoUser
from girder.models.setting import Setting
from girder.models.user import User
from girder.settings import SettingKey
from girder.utility import mail_utils


class Group(Resource):
    """API Endpoint for groups."""

    def __init__(self):
        super(Group, self).__init__()
        self.resourceName = 'group'
        self._model = GroupModel()

        self.route('DELETE', (':id',), self.deleteGroup)
        self.route('DELETE', (':id', 'member'), self.removeFromGroup)
        self.route('DELETE', (':id', 'moderator'), self.demote)
        self.route('DELETE', (':id', 'admin'), self.demote)
        self.route('GET', (), self.find)
        self.route('GET', ('open',), self.getOpenGroups)
        self.route('GET', (':id',), self.getGroup)
        self.route('GET', (':id', 'access'), self.getGroupAccess)
        self.route('GET', (':id', 'invitation'), self.getGroupInvitations)
        self.route('GET', (':id', 'member'), self.listMembers)
        self.route('POST', (), self.createGroup)
        self.route('POST', (':id', 'invitation'), self.inviteToGroup)
        self.route('POST', (':id', 'member'), self.joinGroup)
        self.route('POST', (':id', 'moderator'), self.promoteToModerator)
        self.route('POST', (':id', 'admin'), self.promoteToAdmin)
        self.route('PUT', (':id',), self.updateGroup)
        self.route('PUT', (':id', 'access'), self.updateGroupAccess)

    @access.public
    @filtermodel(model=GroupModel)
    @autoDescribeRoute(
        Description('Search for groups or list all groups.')
        .param('text', 'Pass this to perform a full-text search for groups.', required=False)
        .param('exact', 'If true, only return exact name matches. This is '
               'case sensitive.', required=False, dataType='boolean', default=False)
        .pagingParams(defaultSort='name')
        .errorResponse()
    )
    def find(self, text, exact, limit, offset, sort):
        user = self.getCurrentUser()
        if text is not None:
            if exact:
                groupList = self._model.find(
                    {'name': text}, offset=offset, limit=limit, sort=sort)
            else:
                groupList = self._model.textSearch(
                    text, user=user, offset=offset, limit=limit, sort=sort)
        else:
            groupList = self._model.list(
                user=user, offset=offset, limit=limit, sort=sort)
        return groupList

    @access.public
    @filtermodel(model=GroupModel)
    @autoDescribeRoute(
        Description('List all groups with open registration.')
        .pagingParams(defaultSort='name')
        .errorResponse()
    )
    def getOpenGroups(self, limit, offset, sort):
        groupList = self._model.find(
            query={'openRegistration': True},
            limit=limit,
            offset=offset,
            sort=sort
        )
        return groupList

    @access.user
    @filtermodel(model=GroupModel)
    @autoDescribeRoute(
        Description('Create a new group.')
        .responseClass('Group')
        .notes('Must be logged in.')
        .param('name', 'Unique name for the group.', strip=True)
        .param('description', 'Description of the group.', required=False,
               default='', strip=True)
        .param(
            'openRegistration',
            'Whether users can join without being invited.',
            required=False,
            dataType='boolean',
            default=False
        )
        .param('public', 'Whether the group should be publicly visible.',
               required=False, dataType='boolean', default=False)
        .errorResponse()
        .errorResponse('Write access was denied on the parent', 403)
    )
    def createGroup(self, name, description, openRegistration, public):
        return(self._model.createGroup(
            name=name,
            creator=self.getCurrentUser(),
            description=description,
            openRegistration=openRegistration,
            public=public
        ))

    @access.public
    @filtermodel(model=GroupModel)
    @autoDescribeRoute(
        Description('Get a group by ID.')
        .responseClass('Group')
        .modelParam('id', model=GroupModel, level=AccessType.READ)
        .errorResponse('ID was invalid.')
        .errorResponse('Read access was denied for the group.', 403)
    )
    def getGroup(self, group):
        # Add in the current setting for adding to groups
        group['_addToGroupPolicy'] = Setting().get(SettingKey.ADD_TO_GROUP_POLICY)
        return group

    @access.public
    @filtermodel(model=GroupModel, addFields={'access', 'requests'})
    @autoDescribeRoute(
        Description('Get the access control list for a group.')
        .responseClass('Group')
        .modelParam('id', model=GroupModel, level=AccessType.READ)
        .errorResponse('ID was invalid.')
        .errorResponse('Read access was denied for the group.', 403)
    )
    def getGroupAccess(self, group):
        groupModel = self._model
        group['access'] = groupModel.getFullAccessList(group)
        group['requests'] = list(groupModel.getFullRequestList(group))
        return group

    @access.user
    @filtermodel(model=GroupModel, addFields={'access'})
    @autoDescribeRoute(
        Description('Update the access control list for a group.')
        .modelParam('id', model=GroupModel, level=AccessType.WRITE)
        .jsonParam('access', 'The JSON-encoded access control list.', requireObject=True)
        .errorResponse('ID was invalid.')
        .errorResponse('Admin access was denied for the user.', 403)
    )
    def updateGroupAccess(self, group, access):
        return self._model.setAccessList(
            group, access, save=True)

    @access.public
    @filtermodel(model=User)
    @autoDescribeRoute(
        Description('Show outstanding invitations for a group.')
        .responseClass('Group')
        .modelParam('id', model=GroupModel, level=AccessType.READ)
        .pagingParams(defaultSort='lastName')
        .errorResponse()
        .errorResponse('Read access was denied for the group.', 403)
    )
    def getGroupInvitations(self, group, limit, offset, sort):
        return self._model.getInvites(group, limit, offset, sort)

    @access.user
    @filtermodel(model=GroupModel)
    @autoDescribeRoute(
        Description('Update a group by ID.')
        .modelParam('id', model=GroupModel, level=AccessType.WRITE)
        .param('name', 'The name to set on the group.', required=False, strip=True)
        .param('description', 'Description for the group.', required=False, strip=True)
        .param(
            'openRegistration',
            'Whether users can join without being invited.',
            required=False,
            dataType='boolean'
        )
        .param('public', 'Whether the group should be publicly visible', dataType='boolean',
               required=False)
        .param('addAllowed', 'Can admins or moderators directly add members '
               'to this group?  Only system administrators are allowed to '
               'set this field', required=False,
               enum=['default', 'no', 'yesmod', 'yesadmin'])
        .errorResponse()
        .errorResponse('Write access was denied for the group.', 403)
    )
    def updateGroup(
        self,
        group,
        name,
        description,
        openRegistration,
        public,
        addAllowed
    ):
        if public is not None:
            self._model.setPublic(group, public)

        if openRegistration is not None:
            group['openRegistration'] = openRegistration
        if name is not None:
            group['name'] = name
        if description is not None:
            group['description'] = description
        if addAllowed is not None:
            self.requireAdmin(self.getCurrentUser())
            group['addAllowed'] = addAllowed

        return(self._model.updateGroup(group))

    @access.user
    @filtermodel(model=GroupModel, addFields={'access', 'requests'})
    @autoDescribeRoute(
        Description('Request to join a group, or accept an invitation to join.')
        .responseClass('Group')
        .modelParam('id', model=GroupModel, force=True)
        .errorResponse('ID was invalid.')
        .errorResponse('You were not invited to this group, or do not have '
                       'read access to it.', 403) # TODO: Update permissions error handling
    )
    def joinGroup(self, group):
        groupModel = self._model
        group = groupModel.joinGroup(group, self.getCurrentUser())
        group['access'] = groupModel.getFullAccessList(group)
        group['requests'] = list(groupModel.getFullRequestList(group))
        return({'_id': group['_id'], 'name': group['name']})

    @access.public
    @filtermodel(model=User)
    @autoDescribeRoute(
        Description('List members of a group.')
        .modelParam('id', model=GroupModel, level=AccessType.READ)
        .pagingParams(defaultSort='lastName')
        .errorResponse('ID was invalid.')
        .errorResponse('Read access was denied for the group.', 403)
    )
    def listMembers(self, group, limit, offset, sort):
        return self._model.listMembers(group, offset=offset, limit=limit, sort=sort)

    @access.user
    @filtermodel(model=GroupModel, addFields={'access', 'requests'})
    @autoDescribeRoute(
        Description(
            "Invite a user to join a group, or accept a user's request to join."
        )
        .responseClass('Group')
        .notes('The "force" option to this endpoint is only available to '
               'administrators and can be used to bypass the invitation process'
               ' and instead add the user directly to the group.')
        .modelParam('id', model=GroupModel, level=AccessType.WRITE)
        .modelParam(
            'userId',
            'The ID of the user to invite or accept. Alternatively, provide '
            '`email`.',
            model=User,
            destName='userToInvite',
            level=AccessType.READ,
            paramType='form',
            required=False
        )
        .param(
            'email',
            'Email address of user to invite. Alternatively, provide `userId`.',
            required=False
        )
        .param(
            'level',
            'The access level the user will be given when they accept the '
            'invitation.',
            required=False,
            dataType='integer',
            default=AccessType.READ
        )
        .param(
            'quiet',
            'If you do not want this action to send an email to '
            'the target user, set this to true.',
            dataType='boolean',
            required=False,
            default=False
        )
        .param(
            'force',
            'Add user directly rather than sending an invitation '
            '(admin-only option).',
            dataType='boolean',
            required=False,
            default=False
        )
        .errorResponse()
        .errorResponse('Write access was denied for the group.', 403)
    )
    def inviteToGroup(
        self,
        group,
        userToInvite=None,
        email=None,
        level=AccessType.READ,
        quiet=False,
        force=False
    ):
        if ((
            userToInvite is None and email is None
        ) or (
            userToInvite is not None and email is not None
        )):
            raise ValidationException(
                "`POST /group/{id}/invitation` requires exactly one of `userID`"
                "and `email`."
            )
        groupModel = self._model
        user = self.getCurrentUser()
        if email is not None:
            userToInvite = User().findOne(query={"email": email}, force=True)
        if userToInvite is None:
            userToInvite = ProtoUser().createProtoUser(email=email)
            try:
                group["queue"] = list(set([email, *group.get("queue", [])]))
            except:
                group["queue"] = list(set([email]))
            groupModel.updateGroup(group)
            # TODO: send email to invite user
            return(group)
        if force:
            if not user['admin']:
                mustBeAdmin = True
                addPolicy = Setting().get(SettingKey.ADD_TO_GROUP_POLICY)
                addGroup = group.get('addAllowed', 'default')
                if addGroup not in ['no', 'yesadmin', 'yesmod']:
                    addGroup = addPolicy
                if (groupModel.hasAccess(
                        group, user, AccessType.ADMIN)
                        and ('mod' in addPolicy or 'admin' in addPolicy)
                        and addGroup.startswith('yes')):
                    mustBeAdmin = False
                elif (groupModel.hasAccess(
                        group, user, AccessType.WRITE)
                        and 'mod' in addPolicy
                        and addGroup == 'yesmod'):
                    mustBeAdmin = False
                if mustBeAdmin:
                    self.requireAdmin(user)
            groupModel.addUser(group, userToInvite, level=level)
        else:
            # Can only invite into access levels that you yourself have
            groupModel.requireAccess(group, user, level)
            groupModel.inviteUser(group, userToInvite, level)

            if not quiet:
                html = mail_utils.renderTemplate('groupInvite.mako', {
                    'userToInvite': userToInvite,
                    'user': user,
                    'group': group
                })
                mail_utils.sendMail(
                    "%s: You've been invited to a group" % Setting().get(SettingKey.BRAND_NAME),
                    html,
                    [userToInvite['email']]
                )

        group['access'] = groupModel.getFullAccessList(group)
        group['requests'] = list(groupModel.getFullRequestList(group))
        return(group)

    @access.user
    @filtermodel(model=GroupModel, addFields={'access'})
    @autoDescribeRoute(
        Description('Promote a member to be a moderator of the group.')
        .responseClass('Group')
        .modelParam('id', model=GroupModel, level=AccessType.ADMIN)
        .modelParam('userId', 'The ID of the user to promote.', model=User,
                    level=AccessType.READ, paramType='formData')
        .errorResponse('ID was invalid.')
        .errorResponse("You don't have permission to promote users.", 403)
    )
    def promoteToModerator(self, group, user):
        return self._promote(group, user, AccessType.WRITE)

    @access.user
    @filtermodel(model=GroupModel, addFields={'access'})
    @autoDescribeRoute(
        Description('Promote a member to be an administrator of the group.')
        .responseClass('Group')
        .modelParam('id', model=GroupModel, level=AccessType.ADMIN)
        .modelParam('userId', 'The ID of the user to promote.', model=User,
                    level=AccessType.READ, paramType='formData')
        .errorResponse('ID was invalid.')
        .errorResponse("You don't have permission to promote users.", 403)
    )
    def promoteToAdmin(self, group, user):
        return self._promote(group, user, AccessType.ADMIN)

    def _promote(self, group, user, level):
        """
        Promote a user to moderator or administrator.

        :param group: The group to promote within.
        :param user: The user to promote.
        :param level: Either WRITE or ADMIN, for moderator or administrator.
        :type level: AccessType
        :returns: The updated group document.
        """
        if not group['_id'] in user.get('groups', []):
            raise AccessException('That user is not a group member.')

        group = self._model.setUserAccess(group, user, level=level, save=True)
        group['access'] = self._model.getFullAccessList(group)
        return group

    @access.user
    @filtermodel(model=GroupModel, addFields={'access', 'requests'})
    @autoDescribeRoute(
        Description('Demote a user to a normal group member.')
        .responseClass('Group')
        .modelParam('id', model=GroupModel, level=AccessType.ADMIN)
        .modelParam('userId', 'The ID of the user to demote.', model=User,
                    level=AccessType.READ, paramType='formData')
        .errorResponse()
        .errorResponse("You don't have permission to demote users.", 403)
    )
    def demote(self, group, user):
        groupModel = self._model
        group = groupModel.setUserAccess(group, user, level=AccessType.READ, save=True)
        group['access'] = groupModel.getFullAccessList(group)
        group['requests'] = list(groupModel.getFullRequestList(group))
        return group

    @access.user
    @filtermodel(model=GroupModel, addFields={'access', 'requests'})
    @autoDescribeRoute(
        Description('Remove a user from a group, or uninvite them.')
        .responseClass('Group')
        .notes('If the specified user is not yet a member of the group, this '
               'will delete any outstanding invitation or membership request for '
               'the user. Passing no userId parameter will assume that the '
               'current user is removing themself.')
        .modelParam('id', model=GroupModel, force=True)
        .modelParam('userId', 'The ID of the user to remove. If not passed, will '
                    'remove yourself from the group.', required=False, model=User,
                    force=True, destName='userToRemove', paramType='formData')
        .param(
            'delete',
            'Delete existing user data associated with this group membership?',
            dataType='boolean',
            required=False,
            default=False
        )
        .errorResponse()
        .errorResponse("You don't have permission to remove that user.", 403)
    )
    def removeFromGroup(self, group, userToRemove, delete):
        user = self.getCurrentUser()
        if not (bool(
            group.get('_id') in [
                *user.get('groups', []),
                *user.get('formerGroups', []),
                *[
                    g.get('groupId') for g  in [
                        *user.get('groupInvites', []),
                        *user.get('declinedInvites', [])
                    ]
                ]
            ]
        )):
            raise AccessException(message="You haven't been invited to that group.")
        else:
            groupModel = self._model
            if userToRemove is None:
                # Assume user is removing themself from the group
                userToRemove = user

            # # If removing someone else, you must have at least as high an
            # # access level as they do, and you must have at least write access
            # # to remove any user other than yourself.
            # if user['_id'] != userToRemove['_id']:
            #     if groupModel.hasAccess(group, userToRemove, AccessType.ADMIN):
            #         groupModel.requireAccess(group, user, AccessType.ADMIN)
            #     else:
            #         groupModel.requireAccess(group, user, AccessType.WRITE)
            group = groupModel.removeUser(group, userToRemove, delete)
            group['access'] = groupModel.getFullAccessList(group)
            group['requests'] = list(groupModel.getFullRequestList(group))
            return(group)

    @access.user
    @autoDescribeRoute(
        Description('Delete a group by ID.')
        .modelParam('id', model=GroupModel, level=AccessType.ADMIN)
        .errorResponse('ID was invalid.')
        .errorResponse('Admin access was denied for the group.', 403)
    )
    def deleteGroup(self, group):
        self._model.remove(group)
        return {'message': 'Deleted the group %s.' % group['name']}
